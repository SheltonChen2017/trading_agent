"""Assistant-owned definition of which code produced a runtime record.

The research repository owns ``data.runtime_identity``. The trading assistant
keeps the same strict lineage behavior privately so neither product must import
the other after extraction. The separation boundary suite holds the two
implementations behavior-identical while they remain in this repository.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
_HEX = frozenset("0123456789abcdef")
_RUNTIME_SOURCE_PATHS = (
    "assistant",
    "backtest",
    "data",
    "execution",
    "ml",
    "risk",
    "research",
    "scripts",
    "signals",
    "strategies",
    "baskets.py",
    "config.py",
    "market_analytics.py",
)


class RuntimeIdentityError(RuntimeError):
    """The assistant runtime cannot be attributed to an exact commit."""


def _run(arguments: list[str], repository: Path) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            arguments,
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeIdentityError(
            f"could not determine the runtime commit ({' '.join(arguments)}): {exc}"
        ) from exc


def current_commit(
    *,
    require_clean: bool = True,
    repository: Path | None = None,
    expected_commit: str | None = None,
) -> str:
    """Return the exact commit this assistant runtime is attributable to.

    ``require_clean`` uses an explicit ``git status`` policy rather than
    ``git diff``: untracked files are part of the runtime too, and the weaker
    check can stamp a commit while imported code is absent from that commit.
    Command-line untracked/submodule options override user or repository
    configuration that could otherwise weaken the check.

    ``expected_commit`` is an assertion, never an override. This lets a
    reviewed invocation bind itself to a declared commit without allowing a
    caller-supplied hash to replace the identity of the code actually running.
    """
    root = Path(repository) if repository is not None else _REPOSITORY_ROOT
    commit = _run(["git", "rev-parse", "HEAD"], root).stdout.strip()
    if len(commit) not in (40, 64) or any(c not in _HEX for c in commit):
        raise RuntimeIdentityError("git HEAD is not a canonical commit hash")
    if expected_commit is not None:
        if (
            not isinstance(expected_commit, str)
            or len(expected_commit) not in (40, 64)
            or any(c not in _HEX for c in expected_commit)
        ):
            raise RuntimeIdentityError(
                "expected code commit is not a canonical commit hash"
            )
        if expected_commit != commit:
            raise RuntimeIdentityError(
                f"expected code commit {expected_commit} does not match "
                f"runtime HEAD {commit}"
            )
    if require_clean:
        status = _run(
            [
                "git",
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--ignore-submodules=none",
            ],
            root,
        ).stdout.strip()
        if status:
            raise RuntimeIdentityError(
                "the working tree has uncommitted or untracked changes, so this "
                "runtime is not represented by any commit. Evidence recorded now "
                "would carry a lineage claim that is not true."
            )
        ignored = _run(
            [
                "git",
                "ls-files",
                "--others",
                "--ignored",
                "--exclude-standard",
                "--",
                *_RUNTIME_SOURCE_PATHS,
            ],
            root,
        ).stdout.splitlines()
        ignored_source = sorted(
            path for path in ignored if Path(path).suffix.lower() in {".py", ".pyi"}
        )
        if ignored_source:
            raise RuntimeIdentityError(
                "ignored Python source can alter this runtime without belonging "
                f"to the recorded commit: {ignored_source}"
            )
    return commit


__all__ = ["RuntimeIdentityError", "current_commit"]
