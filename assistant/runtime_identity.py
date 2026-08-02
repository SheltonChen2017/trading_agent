"""The single definition of "which code produced this record".

Four scripts previously carried their own ``_current_commit()`` and had
drifted into four different strictness levels. The dangerous pair used
``git diff --quiet HEAD --``, which reports a clean tree while untracked
files sit in it:

    $ echo "" > ml/probe.py          # untracked
    $ git diff --quiet HEAD -- && echo clean
    clean

So a shadow run could stamp observations with a commit while importing a
module that commit does not contain, and a research report could be
stamped from a fully dirty tree. Evidence lineage is only worth recording
if the recorded identity is true, so this module keeps one strict
definition and every caller uses it.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
_HEX = frozenset("0123456789abcdef")


class RuntimeIdentityError(RuntimeError):
    """The runtime cannot be attributed to an exact commit."""


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
    *, require_clean: bool = True, repository: Path | None = None
) -> str:
    """Return the exact commit this runtime is attributable to.

    ``require_clean`` uses ``git status --porcelain`` rather than
    ``git diff``: untracked files are part of the runtime too, and the
    weaker check is what let an untracked module hide inside a "clean"
    lineage claim.
    """
    root = Path(repository) if repository is not None else _REPOSITORY_ROOT
    commit = _run(["git", "rev-parse", "HEAD"], root).stdout.strip()
    if len(commit) not in (40, 64) or any(c not in _HEX for c in commit):
        raise RuntimeIdentityError("git HEAD is not a canonical commit hash")
    if require_clean:
        status = _run(["git", "status", "--porcelain"], root).stdout.strip()
        if status:
            raise RuntimeIdentityError(
                "the working tree has uncommitted or untracked changes, so this "
                "runtime is not represented by any commit. Evidence recorded now "
                "would carry a lineage claim that is not true."
            )
    return commit
