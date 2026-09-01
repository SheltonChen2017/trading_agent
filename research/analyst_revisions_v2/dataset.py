"""Immutable publication and strict loading of normalized ARV2 datasets."""
from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
import threading
import uuid
import weakref
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from . import CANONICAL_EVENT_SCHEMA, DATASET_SCHEMA
from .canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    require_canonical_json_bytes,
    require_exact_keys,
    require_git_object,
    require_identifier,
    require_int,
    require_sha256,
    sha256_bytes,
)
from .contracts import CanonicalSourceEvent
from .normalization import (
    NORMALIZATION_RESULT_SCHEMA,
    REFUSAL_SCHEMA,
    NormalizationProvenance,
    NormalizationRefusal,
    NormalizationResult,
    revalidate_normalization_result,
)
from .snapshot import (
    SNAPSHOT_MANIFEST_SCHEMA,
    VerifiedSnapshot,
    revalidate_verified_snapshot,
)


DATASET_MANIFEST_FILENAME = "manifest.json"
EVENTS_FILENAME = "events.jsonl"
REFUSALS_FILENAME = "refusals.jsonl"
PACKAGE_CODE_HASH_SCHEMA = "arv2-package-code-hash-v1"

_DATASET_FILES = frozenset(
    {DATASET_MANIFEST_FILENAME, EVENTS_FILENAME, REFUSALS_FILENAME}
)
_MANIFEST_KEYS = frozenset(
    {
        "schema",
        "dataset_id",
        "canonical_event_schema",
        "refusal_schema",
        "normalization_result_schema",
        "snapshot_schema",
        "snapshot_id",
        "snapshot_manifest_sha256",
        "provider_contract_id",
        "provider_contract_sha256",
        "source_row_count",
        "normalizer_config_sha256",
        "normalizer_code_sha256",
        "evidence_epoch_id",
        "build_recipe_id",
        "build_recipe_sha256",
        "producing_commit",
        "producing_tree",
        "normalization_result_sha256",
        "events_filename",
        "events_sha256",
        "event_count",
        "refusals_filename",
        "refusals_sha256",
        "refusal_count",
    }
)


class DatasetVerificationError(CanonicalEvidenceError):
    """A normalized dataset is mutable, incomplete, or incorrectly bound."""


_DATASET_AUTHORITIES: dict[
    int, tuple[weakref.ReferenceType["NormalizedDataset"], Path, str]
] = {}
_DATASET_AUTHORITIES_LOCK = threading.RLock()


@dataclasses.dataclass(frozen=True)
class CleanGitLineage:
    """A clean, exact Git commit/tree pair used to produce an artifact."""

    repository_root: Path
    producing_commit: str
    producing_tree: str

    def __post_init__(self) -> None:
        if not isinstance(self.repository_root, Path):
            raise DatasetVerificationError("repository_root must be a pathlib.Path")
        if not self.repository_root.is_absolute():
            raise DatasetVerificationError("repository_root must be absolute")
        require_git_object(self.producing_commit, "producing_commit")
        require_git_object(self.producing_tree, "producing_tree")


_READ_ONLY_GIT_SUBCOMMANDS = frozenset(
    {"cat-file", "ls-files", "rev-parse", "show", "status"}
)


def _is_canonical_git_path(value: str) -> bool:
    """Return whether ``value`` is one inert repository-relative path."""

    if (
        type(value) is not str
        or not value
        or "\\" in value
        or ":" in value
        or any(character in value for character in "*?[")
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and path.as_posix() == value
        and all(part not in ("", ".", "..") for part in path.parts)
    )


def _is_canonical_commit(value: str) -> bool:
    return (
        type(value) is str
        and len(value) in (40, 64)
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_commit_blob(value: str) -> bool:
    if type(value) is not str or ":" not in value:
        return False
    commit, separator, path = value.partition(":")
    return (
        separator == ":"
        and (commit == "HEAD" or _is_canonical_commit(commit))
        and _is_canonical_git_path(path)
    )


def _require_read_only_git_arguments(arguments: Sequence[str]) -> tuple[str, ...]:
    """Accept only the exact inert Git query shapes used by this lane."""

    if isinstance(arguments, (str, bytes)):
        raise DatasetVerificationError(
            "Git arguments are not an approved read-only argument shape"
        )
    rendered = tuple(arguments)
    if (
        not rendered
        or any(type(argument) is not str for argument in rendered)
        or rendered[0] not in _READ_ONLY_GIT_SUBCOMMANDS
    ):
        raise DatasetVerificationError(
            "Git subcommand is not on the read-only allowlist: "
            f"{rendered[0] if rendered else '<empty>'}"
        )

    approved = False
    if rendered[0] == "rev-parse":
        approved = rendered in {
            ("rev-parse", "--show-toplevel"),
            ("rev-parse", "--verify", "HEAD"),
            ("rev-parse", "--verify", "HEAD^{tree}"),
        }
    elif rendered[0] == "status":
        prefix = ("status", "--porcelain=v1", "--untracked-files=all")
        approved = rendered == prefix or (
            len(rendered) > len(prefix) + 1
            and rendered[: len(prefix)] == prefix
            and rendered[len(prefix)] == "--"
            and all(_is_canonical_git_path(path) for path in rendered[len(prefix) + 1 :])
        )
    elif rendered[0] == "ls-files":
        approved = (
            len(rendered) >= 4
            and rendered[1:3] in (("-z", "--"), ("--error-unmatch", "--"))
            and all(_is_canonical_git_path(path) for path in rendered[3:])
        )
    elif rendered[0] == "show":
        approved = len(rendered) == 2 and _is_commit_blob(rendered[1])
    elif rendered[0] == "cat-file":
        approved = (
            len(rendered) == 3
            and rendered[1] == "-e"
            and rendered[2].endswith("^{commit}")
            and _is_canonical_commit(rendered[2][:-9])
        )

    if not approved:
        raise DatasetVerificationError(
            "Git arguments are not an approved read-only argument shape"
        )
    return rendered


def _read_only_git_environment() -> dict[str, str]:
    """Remove inherited Git controls and disable optional writes/prompts."""

    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    environment.update(
        {
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_PAGER": "cat",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return environment


def _git_config_query_environment() -> dict[str, str]:
    """Permit data-only config reads while blocking environment injection."""

    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    environment.update(
        {
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_PAGER": "cat",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return environment


def _effective_git_conversion_value(
    repository_root: Path,
    key: str,
    *,
    default: str,
    aliases: Mapping[str, str],
) -> str:
    """Read and strictly normalize one non-executable checkout setting."""

    command = [
        "git",
        "--no-optional-locks",
        "--no-replace-objects",
        "-C",
        str(repository_root),
        "config",
        "--get",
        key,
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            shell=False,
            env=_git_config_query_environment(),
        )
    except (OSError, UnicodeError) as exc:
        raise DatasetVerificationError(
            "Git conversion configuration could not be read"
        ) from exc
    if completed.returncode == 1 and not completed.stdout:
        return default
    if completed.returncode != 0:
        raise DatasetVerificationError(
            "Git conversion configuration could not be read"
        )
    raw = completed.stdout.strip().lower()
    try:
        return aliases[raw]
    except KeyError as exc:
        raise DatasetVerificationError(
            f"unsupported Git conversion configuration for {key}"
        ) from exc


def _refuse_local_git_filter_drivers(repository_root: Path) -> None:
    """Refuse status when repository config can execute content filters."""

    command = [
        "git",
        "--no-optional-locks",
        "--no-replace-objects",
        "-C",
        str(repository_root),
        "config",
        "--includes",
        "--name-only",
        "--get-regexp",
        r"^filter\.",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            shell=False,
            env=_read_only_git_environment(),
        )
    except (OSError, UnicodeError) as exc:
        raise DatasetVerificationError(
            "local Git filter configuration could not be audited"
        ) from exc
    if completed.returncode == 1 and not completed.stdout:
        return
    if completed.returncode != 0:
        raise DatasetVerificationError(
            "local Git filter configuration could not be audited"
        )
    executable_suffixes = (".clean", ".process", ".smudge")
    if any(
        name.strip().lower().endswith(executable_suffixes)
        for name in completed.stdout.splitlines()
    ):
        raise DatasetVerificationError(
            "local Git filter driver is forbidden at the read-only boundary"
        )


def _refuse_nonstandard_git_index_entries(repository_root: Path) -> None:
    """Reject index flags that can make a changed working file look clean."""

    command = [
        "git",
        "--no-optional-locks",
        "--no-replace-objects",
        "-c",
        "core.commitGraph=false",
        "-c",
        "core.fsmonitor=false",
        "-C",
        str(repository_root),
        "ls-files",
        "-v",
        "-z",
        "--",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            shell=False,
            env=_read_only_git_environment(),
        )
    except OSError as exc:
        raise DatasetVerificationError("Git index flags could not be audited") from exc
    if completed.returncode != 0:
        raise DatasetVerificationError("Git index flags could not be audited")
    for entry in completed.stdout.split(b"\0"):
        if not entry:
            continue
        if len(entry) < 3 or entry[:2] != b"H ":
            raise DatasetVerificationError(
                "nonstandard Git index flag is forbidden at the clean-lineage boundary"
            )


def _require_worktree_content_matches_index(
    repository_root: Path, status_arguments: tuple[str, ...]
) -> None:
    """Hash tracked working bytes independently of Git's stat-cache shortcut."""

    prefix = ("status", "--porcelain=v1", "--untracked-files=all")
    requested_paths = (
        status_arguments[len(prefix) + 1 :]
        if len(status_arguments) > len(prefix)
        else ()
    )
    inventory_command = [
        "git",
        "--no-optional-locks",
        "--no-replace-objects",
        "-c",
        "core.fsmonitor=false",
        "-C",
        str(repository_root),
        "ls-files",
        "-s",
        "-z",
        "--",
        *requested_paths,
    ]
    try:
        inventory = subprocess.run(
            inventory_command,
            check=False,
            capture_output=True,
            shell=False,
            env=_read_only_git_environment(),
        )
    except OSError as exc:
        raise DatasetVerificationError(
            "Git index content could not be audited"
        ) from exc
    if inventory.returncode != 0:
        raise DatasetVerificationError("Git index content could not be audited")

    entries: list[tuple[str, str]] = []
    for entry in inventory.stdout.split(b"\0"):
        if not entry:
            continue
        metadata, separator, raw_path = entry.partition(b"\t")
        fields = metadata.split()
        if separator != b"\t" or len(fields) != 3:
            raise DatasetVerificationError("Git index content is malformed")
        mode, raw_oid, stage = fields
        try:
            oid = raw_oid.decode("ascii", errors="strict")
            relative_path = raw_path.decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise DatasetVerificationError(
                "Git index path or object id is not canonical text"
            ) from exc
        if (
            mode not in (b"100644", b"100755")
            or stage != b"0"
            or not _is_canonical_commit(oid)
            or not _is_canonical_git_path(relative_path)
        ):
            raise DatasetVerificationError(
                "Git index content is not a canonical regular-file inventory"
            )
        entries.append((relative_path, oid))

    conversion_options = _read_only_git_global_options(
        repository_root, include_conversion=True
    )
    try:
        resolved_root = repository_root.resolve(strict=True)
    except OSError as exc:
        raise DatasetVerificationError("repository root is not accessible") from exc
    for relative_path, _expected_oid in entries:
        working_path = repository_root / PurePosixPath(relative_path)
        try:
            working_path.resolve(strict=True).relative_to(resolved_root)
        except (OSError, ValueError) as exc:
            raise DatasetVerificationError(
                "tracked working file is absent or escapes the repository"
            ) from exc
        cursor = working_path
        while cursor != repository_root:
            if cursor.is_symlink() or (
                cursor.is_junction() if hasattr(cursor, "is_junction") else False
            ):
                raise DatasetVerificationError(
                    "tracked working file cannot cross a symlink or junction"
                )
            cursor = cursor.parent
        if not working_path.is_file():
            raise DatasetVerificationError(
                "tracked working path is not a regular file"
            )

    if not entries:
        return
    attribute_command = [
        "git",
        *_read_only_git_global_options(repository_root, include_conversion=False),
        "-C",
        str(repository_root),
        "check-attr",
        "-z",
        "--stdin",
        "ident",
    ]
    encoded_paths = b"\0".join(
        relative_path.encode("utf-8", errors="strict")
        for relative_path, _oid in entries
    ) + b"\0"
    try:
        attributes = subprocess.run(
            attribute_command,
            check=False,
            capture_output=True,
            input=encoded_paths,
            shell=False,
            env=_read_only_git_environment(),
        )
    except (OSError, UnicodeError) as exc:
        raise DatasetVerificationError(
            "tracked working attributes could not be audited"
        ) from exc
    attribute_fields = attributes.stdout.split(b"\0")
    if attribute_fields and not attribute_fields[-1]:
        attribute_fields.pop()
    expected_attribute_fields: list[bytes] = []
    for relative_path, _oid in entries:
        expected_attribute_fields.extend(
            (relative_path.encode("utf-8"), b"ident", b"unspecified")
        )
    if attributes.returncode != 0 or len(attribute_fields) != len(
        expected_attribute_fields
    ):
        raise DatasetVerificationError(
            "tracked working attributes could not be audited"
        )
    for offset in range(0, len(attribute_fields), 3):
        actual_path, actual_name, actual_value = attribute_fields[offset : offset + 3]
        expected_path = expected_attribute_fields[offset]
        if actual_path != expected_path or actual_name != b"ident":
            raise DatasetVerificationError(
                "tracked working attributes could not be audited"
            )
        if actual_value not in (b"unspecified", b"unset"):
            raise DatasetVerificationError(
                "Git ident expansion is forbidden at the clean-lineage boundary"
            )

    command = [
        "git",
        *conversion_options,
        "-C",
        str(repository_root),
        "hash-object",
        "--stdin-paths",
    ]
    try:
        hashed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            input="".join(f"{relative_path}\n" for relative_path, _oid in entries),
            text=True,
            encoding="utf-8",
            errors="strict",
            shell=False,
            env=_read_only_git_environment(),
        )
    except (OSError, UnicodeError) as exc:
        raise DatasetVerificationError(
            "tracked working content could not be hashed"
        ) from exc
    actual_oids = hashed.stdout.splitlines()
    if hashed.returncode != 0 or len(actual_oids) != len(entries):
        raise DatasetVerificationError(
            "tracked working content could not be hashed"
        )
    for (_relative_path, expected_oid), actual_oid in zip(entries, actual_oids):
        if not _is_canonical_commit(actual_oid) or actual_oid != expected_oid:
            raise DatasetVerificationError(
                "tracked working content differs from the Git index"
            )


def _read_only_git_global_options(
    repository_root: Path, *, include_conversion: bool
) -> list[str]:
    options = [
        "--no-optional-locks",
        "--no-replace-objects",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.ignoreStat=false",
        "-c",
        "core.untrackedCache=false",
        "-c",
        "diff.external=",
    ]
    if include_conversion:
        autocrlf = _effective_git_conversion_value(
            repository_root,
            "core.autocrlf",
            default="false",
            aliases={
                "0": "false",
                "1": "true",
                "false": "false",
                "input": "input",
                "no": "false",
                "off": "false",
                "on": "true",
                "true": "true",
                "yes": "true",
            },
        )
        eol = _effective_git_conversion_value(
            repository_root,
            "core.eol",
            default="native",
            aliases={"crlf": "crlf", "lf": "lf", "native": "native"},
        )
        options.extend(
            ("-c", f"core.autocrlf={autocrlf}", "-c", f"core.eol={eol}")
        )
    return options


def _read_only_git_command(
    repository_root: Path, arguments: Sequence[str]
) -> list[str]:
    return [
        "git",
        *_read_only_git_global_options(
            repository_root, include_conversion=arguments[0] == "status"
        ),
        "-C",
        str(repository_root),
        *arguments,
    ]


def _run_git(repository_root: Path, arguments: Sequence[str]) -> str:
    rendered = _require_read_only_git_arguments(arguments)
    if rendered[0] == "status":
        _refuse_local_git_filter_drivers(repository_root)
        _refuse_nonstandard_git_index_entries(repository_root)
        _require_worktree_content_matches_index(repository_root, rendered)
    command = _read_only_git_command(repository_root, rendered)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            shell=False,
            env=_read_only_git_environment(),
        )
    except (OSError, UnicodeError) as exc:
        raise DatasetVerificationError("Git lineage command could not run") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise DatasetVerificationError(f"Git lineage command failed: {detail}")
    return completed.stdout


def _run_git_bytes(repository_root: Path, arguments: Sequence[str]) -> bytes:
    rendered = _require_read_only_git_arguments(arguments)
    if rendered[0] == "status":
        _refuse_local_git_filter_drivers(repository_root)
        _refuse_nonstandard_git_index_entries(repository_root)
        _require_worktree_content_matches_index(repository_root, rendered)
    command = _read_only_git_command(repository_root, rendered)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            shell=False,
            env=_read_only_git_environment(),
        )
    except OSError as exc:
        raise DatasetVerificationError("Git lineage command could not run") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise DatasetVerificationError(f"Git lineage command failed: {detail}")
    return completed.stdout


def read_git_text(repository_root: Path, arguments: Sequence[str]) -> str:
    """Run a shell-free, read-only Git query and return strict UTF-8 text."""
    return _run_git(repository_root, arguments)


def read_git_bytes(repository_root: Path, arguments: Sequence[str]) -> bytes:
    """Run a shell-free, read-only Git query and return exact bytes."""
    return _run_git_bytes(repository_root, arguments)


def _refuse_git_grafts(repository_root: Path) -> None:
    """Reject legacy graft metadata that can forge commit ancestry."""

    command = [
        "git",
        *_read_only_git_global_options(repository_root, include_conversion=False),
        "-C",
        str(repository_root),
        "rev-parse",
        "--path-format=absolute",
        "--git-path",
        "info/grafts",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            shell=False,
            env=_read_only_git_environment(),
        )
    except (OSError, UnicodeError) as exc:
        raise DatasetVerificationError("Git graft metadata could not be audited") from exc
    lines = completed.stdout.splitlines()
    if completed.returncode != 0 or len(lines) != 1 or not lines[0]:
        raise DatasetVerificationError("Git graft metadata could not be audited")
    grafts_path = Path(lines[0].replace("/", os.sep))
    if not grafts_path.is_absolute():
        grafts_path = repository_root / grafts_path
    try:
        grafts_path.parent.resolve(strict=True)
    except OSError as exc:
        raise DatasetVerificationError("Git graft metadata could not be audited") from exc
    if (
        grafts_path.exists()
        or grafts_path.is_symlink()
        or (grafts_path.is_junction() if hasattr(grafts_path, "is_junction") else False)
    ):
        raise DatasetVerificationError(
            "legacy Git graft metadata is forbidden at the ancestry boundary"
        )


def git_commit_is_ancestor(
    repository_root: Path, ancestor: str, descendant: str
) -> bool:
    """Return Git's exact ancestry result; reject command failures other than no."""
    require_git_object(ancestor, "ancestor")
    if descendant != "HEAD":
        require_git_object(descendant, "descendant")
    _refuse_git_grafts(repository_root)
    try:
        completed = subprocess.run(
            [
                "git",
                *_read_only_git_global_options(
                    repository_root, include_conversion=False
                ),
                "-C",
                str(repository_root),
                "merge-base",
                "--is-ancestor",
                ancestor,
                descendant,
            ],
            check=False,
            capture_output=True,
            shell=False,
            env=_read_only_git_environment(),
        )
    except OSError as exc:
        raise DatasetVerificationError("Git ancestry query could not run") from exc
    _refuse_git_grafts(repository_root)
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    detail = completed.stderr.decode("utf-8", errors="replace").strip()
    raise DatasetVerificationError(f"Git ancestry query failed: {detail}")


def capture_clean_git_lineage(repository_root: str | Path) -> CleanGitLineage:
    """Capture HEAD only when the supplied repository is completely clean."""
    root = Path(repository_root).expanduser().resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise DatasetVerificationError("repository_root must be a regular directory")
    top_level = Path(
        _run_git(root, ("rev-parse", "--show-toplevel"))
        .strip()
        .replace("/", os.sep)
    ).resolve(strict=True)
    if top_level != root:
        raise DatasetVerificationError("repository_root is not the Git top level")
    status = _run_git(root, ("status", "--porcelain=v1", "--untracked-files=all"))
    if status:
        raise DatasetVerificationError("Git worktree is not clean")
    commit = _run_git(root, ("rev-parse", "--verify", "HEAD")).strip()
    tree = _run_git(root, ("rev-parse", "--verify", "HEAD^{tree}")).strip()
    return CleanGitLineage(root, commit, tree)


def assert_clean_git_lineage(lineage: CleanGitLineage) -> None:
    """Fail if HEAD, its tree, or worktree state changed after capture."""
    if type(lineage) is not CleanGitLineage:
        raise DatasetVerificationError("lineage must be a CleanGitLineage")
    current = capture_clean_git_lineage(lineage.repository_root)
    if (
        current.producing_commit != lineage.producing_commit
        or current.producing_tree != lineage.producing_tree
    ):
        raise DatasetVerificationError("Git lineage changed before publication")


def compute_package_source_sha256(repository_root: str | Path) -> str:
    """Hash the committed bytes of every tracked ARV2 Python source.

    The filesystem inventory must exactly match Git's inventory.  In
    particular, an ignored ``.py`` file cannot enter the declared code hash
    while remaining absent from ``producing_commit``.
    """
    root = Path(repository_root).expanduser().resolve(strict=True)
    package_root = root / "research" / "analyst_revisions_v2"
    if not package_root.is_dir() or package_root.is_symlink():
        raise DatasetVerificationError(
            "repository does not contain a regular ARV2 package directory"
        )
    filesystem_paths: set[str] = set()
    for path in sorted(package_root.rglob("*")):
        if path.is_symlink():
            raise DatasetVerificationError("ARV2 package source cannot contain symlinks")
        if path.is_file() and path.suffix == ".py":
            filesystem_paths.add(path.relative_to(root).as_posix())
    raw_tracked = _run_git_bytes(
        root, ("ls-files", "-z", "--", "research/analyst_revisions_v2")
    )
    try:
        tracked_paths = {
            entry.decode("utf-8", errors="strict")
            for entry in raw_tracked.split(b"\0")
            if entry and entry.endswith(b".py")
        }
    except UnicodeError as exc:
        raise DatasetVerificationError("tracked package path is not UTF-8") from exc
    if not filesystem_paths:
        raise DatasetVerificationError("ARV2 package contains no Python source")
    if filesystem_paths != tracked_paths:
        raise DatasetVerificationError(
            "ARV2 Python source inventory does not exactly match producing_commit; "
            f"untracked_or_ignored={sorted(filesystem_paths - tracked_paths)}, "
            f"missing={sorted(tracked_paths - filesystem_paths)}"
        )
    commit = _run_git(root, ("rev-parse", "--verify", "HEAD")).strip()
    require_git_object(commit, "package source commit")
    inventory: list[dict[str, str]] = []
    for relative in sorted(tracked_paths):
        committed_bytes = _run_git_bytes(root, ("show", f"{commit}:{relative}"))
        inventory.append(
            {"path": relative, "sha256": sha256_bytes(committed_bytes)}
        )
    return sha256_bytes(
        canonical_json_bytes(
            {"schema": PACKAGE_CODE_HASH_SCHEMA, "files": inventory}
        )
    )


def _dataset_identity_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(record)
    payload.pop("dataset_id", None)
    return payload


def _derive_dataset_id(record: Mapping[str, Any]) -> str:
    return "arv2_ds_" + sha256_bytes(
        canonical_json_bytes(_dataset_identity_payload(record))
    )


@dataclasses.dataclass(frozen=True)
class NormalizedDatasetManifest:
    schema: str
    dataset_id: str
    canonical_event_schema: str
    refusal_schema: str
    normalization_result_schema: str
    snapshot_schema: str
    snapshot_id: str
    snapshot_manifest_sha256: str
    provider_contract_id: str
    provider_contract_sha256: str
    source_row_count: int
    normalizer_config_sha256: str
    normalizer_code_sha256: str
    evidence_epoch_id: str
    build_recipe_id: str
    build_recipe_sha256: str
    producing_commit: str
    producing_tree: str
    normalization_result_sha256: str
    events_filename: str
    events_sha256: str
    event_count: int
    refusals_filename: str
    refusals_sha256: str
    refusal_count: int

    def __post_init__(self) -> None:
        if self.schema != DATASET_SCHEMA:
            raise DatasetVerificationError("unsupported normalized dataset schema")
        if self.canonical_event_schema != CANONICAL_EVENT_SCHEMA:
            raise DatasetVerificationError("wrong canonical event schema binding")
        if self.refusal_schema != REFUSAL_SCHEMA:
            raise DatasetVerificationError("wrong refusal schema binding")
        if self.normalization_result_schema != NORMALIZATION_RESULT_SCHEMA:
            raise DatasetVerificationError("wrong normalization result schema binding")
        if self.snapshot_schema != SNAPSHOT_MANIFEST_SCHEMA:
            raise DatasetVerificationError("wrong source snapshot schema binding")
        require_identifier(self.snapshot_id, "snapshot_id")
        require_identifier(self.provider_contract_id, "provider_contract_id")
        require_identifier(self.evidence_epoch_id, "evidence_epoch_id")
        require_identifier(self.build_recipe_id, "build_recipe_id")
        for name in (
            "snapshot_manifest_sha256",
            "provider_contract_sha256",
            "normalizer_config_sha256",
            "normalizer_code_sha256",
            "build_recipe_sha256",
            "normalization_result_sha256",
            "events_sha256",
            "refusals_sha256",
        ):
            require_sha256(getattr(self, name), name)
        require_git_object(self.producing_commit, "producing_commit")
        require_git_object(self.producing_tree, "producing_tree")
        source_count = require_int(
            self.source_row_count, "source_row_count", minimum=1
        )
        event_count = require_int(self.event_count, "event_count", minimum=0)
        refusal_count = require_int(self.refusal_count, "refusal_count", minimum=0)
        if event_count + refusal_count != source_count:
            raise DatasetVerificationError(
                "event_count plus refusal_count must equal source_row_count"
            )
        if self.events_filename != EVENTS_FILENAME:
            raise DatasetVerificationError("events filename is not canonical")
        if self.refusals_filename != REFUSALS_FILENAME:
            raise DatasetVerificationError("refusals filename is not canonical")
        expected_id = _derive_dataset_id(self.to_record())
        if self.dataset_id != expected_id:
            raise DatasetVerificationError("dataset_id does not bind the manifest")

    def to_record(self) -> dict[str, Any]:
        return {field.name: getattr(self, field.name) for field in dataclasses.fields(self)}

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "NormalizedDatasetManifest":
        require_exact_keys(record, _MANIFEST_KEYS, "normalized dataset manifest")
        return cls(**dict(record))


@dataclasses.dataclass(frozen=True, init=False)
class NormalizedDataset:
    manifest: NormalizedDatasetManifest
    snapshot: VerifiedSnapshot
    events: tuple[CanonicalSourceEvent, ...]
    refusals: tuple[NormalizationRefusal, ...]

    pass


def _normalized_dataset_fingerprint(dataset: NormalizedDataset) -> str:
    return sha256_bytes(
        canonical_json_bytes(
            {
                "manifest": dataset.manifest.to_record(),
                "snapshot": {
                    "schema": dataset.snapshot.schema,
                    "snapshot_id": dataset.snapshot.snapshot_id,
                    "manifest_sha256": dataset.snapshot.manifest_sha256,
                    "provider_contract_id": dataset.snapshot.provider_contract_id,
                    "provider_contract_sha256": (
                        dataset.snapshot.provider_contract_sha256
                    ),
                    "source_row_count": dataset.snapshot.source_row_count,
                },
                "events": [event.to_record() for event in dataset.events],
                "refusals": [refusal.to_record() for refusal in dataset.refusals],
            }
        )
    )


def _forget_dataset_authority(
    identity: int, reference: weakref.ReferenceType[NormalizedDataset]
) -> None:
    with _DATASET_AUTHORITIES_LOCK:
        current = _DATASET_AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _DATASET_AUTHORITIES.pop(identity, None)


def _normalized_dataset(
    root: Path,
    manifest: NormalizedDatasetManifest,
    snapshot: VerifiedSnapshot,
    events: tuple[CanonicalSourceEvent, ...],
    refusals: tuple[NormalizationRefusal, ...],
) -> NormalizedDataset:
    if type(manifest) is not NormalizedDatasetManifest:
        raise DatasetVerificationError("manifest must be a typed dataset manifest")
    revalidate_verified_snapshot(snapshot)
    if type(events) is not tuple or any(
        type(event) is not CanonicalSourceEvent for event in events
    ):
        raise DatasetVerificationError("events must be immutable canonical records")
    if type(refusals) is not tuple or any(
        type(refusal) is not NormalizationRefusal for refusal in refusals
    ):
        raise DatasetVerificationError("refusals must be immutable canonical records")
    value = object.__new__(NormalizedDataset)
    object.__setattr__(value, "manifest", manifest)
    object.__setattr__(value, "snapshot", snapshot)
    object.__setattr__(value, "events", events)
    object.__setattr__(value, "refusals", refusals)
    fingerprint = _normalized_dataset_fingerprint(value)
    identity = id(value)
    reference = weakref.ref(
        value, lambda ref, key=identity: _forget_dataset_authority(key, ref)
    )
    with _DATASET_AUTHORITIES_LOCK:
        _DATASET_AUTHORITIES[identity] = (reference, root, fingerprint)
    return value


def revalidate_normalized_dataset(dataset: NormalizedDataset) -> NormalizedDataset:
    """Reload and compare the complete loader-authenticated dataset artifact."""
    if type(dataset) is not NormalizedDataset:
        raise DatasetVerificationError(
            "dataset authority requires an exact NormalizedDataset"
        )
    with _DATASET_AUTHORITIES_LOCK:
        authority = _DATASET_AUTHORITIES.get(id(dataset))
    if authority is None or authority[0]() is not dataset:
        raise DatasetVerificationError(
            "NormalizedDataset is not loader-authenticated authority"
        )
    _, root, expected_fingerprint = authority
    revalidate_verified_snapshot(dataset.snapshot)
    if _normalized_dataset_fingerprint(dataset) != expected_fingerprint:
        raise DatasetVerificationError(
            "NormalizedDataset records changed after loader authentication"
        )
    try:
        reloaded = load_normalized_dataset(root, snapshot=dataset.snapshot)
    except OSError as exc:
        raise DatasetVerificationError(
            "bound normalized dataset artifact is absent or unreadable"
        ) from exc
    if _normalized_dataset_fingerprint(reloaded) != expected_fingerprint:
        raise DatasetVerificationError(
            "normalized manifest, counts, content, or result binding changed"
        )
    return dataset


def _canonical_jsonl(records: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(record) for record in records)


def _write_new_file(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def publish_normalized_dataset(
    output_root: str | Path,
    *,
    result: NormalizationResult,
    lineage: CleanGitLineage,
) -> NormalizedDatasetManifest:
    """Atomically publish a never-overwritten canonical dataset directory."""
    if type(result) is not NormalizationResult:
        raise DatasetVerificationError("result must be a NormalizationResult")
    result = revalidate_normalization_result(result)
    if type(lineage) is not CleanGitLineage:
        raise DatasetVerificationError("lineage must be a CleanGitLineage")
    assert_clean_git_lineage(lineage)
    if result.provenance.producing_commit != lineage.producing_commit:
        raise DatasetVerificationError("normalization commit does not match Git lineage")
    code_hash = compute_package_source_sha256(lineage.repository_root)
    assert_clean_git_lineage(lineage)
    if result.provenance.normalizer_code_sha256 != code_hash:
        raise DatasetVerificationError(
            "normalizer_code_sha256 does not match clean package source"
        )

    target = Path(output_root).expanduser()
    if not target.name or target.name in (".", ".."):
        raise DatasetVerificationError("output_root needs a concrete directory name")
    parent = target.parent.resolve(strict=True)
    target = parent / target.name
    if target.exists() or target.is_symlink():
        raise DatasetVerificationError("immutable dataset target already exists")

    event_bytes = _canonical_jsonl([event.to_record() for event in result.events])
    refusal_bytes = _canonical_jsonl(
        [refusal.to_record() for refusal in result.refusals]
    )
    manifest_fields: dict[str, Any] = {
        "schema": DATASET_SCHEMA,
        "dataset_id": "pending",
        "canonical_event_schema": CANONICAL_EVENT_SCHEMA,
        "refusal_schema": REFUSAL_SCHEMA,
        "normalization_result_schema": NORMALIZATION_RESULT_SCHEMA,
        "snapshot_schema": result.snapshot.schema,
        "snapshot_id": result.snapshot.snapshot_id,
        "snapshot_manifest_sha256": result.snapshot.manifest_sha256,
        "provider_contract_id": result.snapshot.provider_contract_id,
        "provider_contract_sha256": result.snapshot.provider_contract_sha256,
        "source_row_count": result.snapshot.source_row_count,
        "normalizer_config_sha256": result.provenance.normalizer_config_sha256,
        "normalizer_code_sha256": result.provenance.normalizer_code_sha256,
        "evidence_epoch_id": result.provenance.evidence_epoch_id,
        "build_recipe_id": result.provenance.build_recipe_id,
        "build_recipe_sha256": result.provenance.build_recipe_sha256,
        "producing_commit": result.provenance.producing_commit,
        "producing_tree": lineage.producing_tree,
        "normalization_result_sha256": result.result_sha256,
        "events_filename": EVENTS_FILENAME,
        "events_sha256": sha256_bytes(event_bytes),
        "event_count": len(result.events),
        "refusals_filename": REFUSALS_FILENAME,
        "refusals_sha256": sha256_bytes(refusal_bytes),
        "refusal_count": len(result.refusals),
    }
    manifest_fields["dataset_id"] = _derive_dataset_id(manifest_fields)
    manifest = NormalizedDatasetManifest(**manifest_fields)
    manifest_bytes = canonical_json_bytes(manifest.to_record())

    temporary = parent / f".{target.name}.tmp-{uuid.uuid4().hex}"
    temporary.mkdir(mode=0o700, exist_ok=False)
    try:
        _write_new_file(temporary / EVENTS_FILENAME, event_bytes)
        _write_new_file(temporary / REFUSALS_FILENAME, refusal_bytes)
        _write_new_file(temporary / DATASET_MANIFEST_FILENAME, manifest_bytes)
        temporary.rename(target)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return manifest


def _load_canonical_jsonl(
    payload: bytes,
    *,
    name: str,
    record_type: type[CanonicalSourceEvent] | type[NormalizationRefusal],
) -> tuple[CanonicalSourceEvent, ...] | tuple[NormalizationRefusal, ...]:
    if payload and (not payload.endswith(b"\n") or b"\r" in payload):
        raise DatasetVerificationError(f"{name} must be LF-terminated JSONL")
    raw_lines = [] if not payload else payload[:-1].split(b"\n")
    if any(not raw_line for raw_line in raw_lines):
        raise DatasetVerificationError(f"{name} contains a blank JSONL row")
    records: list[CanonicalSourceEvent | NormalizationRefusal] = []
    for index, raw_line in enumerate(raw_lines):
        row_payload = raw_line + b"\n"
        value = require_canonical_json_bytes(row_payload, f"{name}:{index}")
        if not isinstance(value, dict):
            raise DatasetVerificationError(f"{name}:{index} must be an object")
        records.append(record_type.from_record(value))
    return tuple(records)


def load_normalized_dataset(
    root: str | Path,
    *,
    snapshot: VerifiedSnapshot,
) -> NormalizedDataset:
    """Hash first, then strictly parse and reconstruct a typed dataset."""
    if type(snapshot) is not VerifiedSnapshot:
        raise DatasetVerificationError("loader requires a complete VerifiedSnapshot")
    revalidate_verified_snapshot(snapshot)
    try:
        root_path = Path(root).expanduser().resolve(strict=True)
    except OSError as exc:
        raise DatasetVerificationError(
            "dataset root is absent or unreadable"
        ) from exc
    if not root_path.is_dir() or root_path.is_symlink():
        raise DatasetVerificationError("dataset root must be a regular directory")
    actual_files: set[str] = set()
    for path in root_path.iterdir():
        if path.is_symlink() or not path.is_file():
            raise DatasetVerificationError("dataset root may contain only regular files")
        actual_files.add(path.name)
    if actual_files != _DATASET_FILES:
        raise DatasetVerificationError(
            "dataset file inventory is not exact; "
            f"missing={sorted(_DATASET_FILES - actual_files)}, "
            f"extra={sorted(actual_files - _DATASET_FILES)}"
        )

    manifest_bytes = (root_path / DATASET_MANIFEST_FILENAME).read_bytes()
    raw_manifest = require_canonical_json_bytes(
        manifest_bytes, "normalized dataset manifest"
    )
    if not isinstance(raw_manifest, dict):
        raise DatasetVerificationError("normalized dataset manifest must be an object")
    manifest = NormalizedDatasetManifest.from_record(raw_manifest)
    if (
        manifest.snapshot_id != snapshot.snapshot_id
        or manifest.snapshot_manifest_sha256 != snapshot.manifest_sha256
        or manifest.provider_contract_id != snapshot.provider_contract_id
        or manifest.provider_contract_sha256 != snapshot.provider_contract_sha256
        or manifest.source_row_count != snapshot.source_row_count
    ):
        raise DatasetVerificationError("dataset does not bind the supplied snapshot")

    event_bytes = (root_path / EVENTS_FILENAME).read_bytes()
    refusal_bytes = (root_path / REFUSALS_FILENAME).read_bytes()
    if sha256_bytes(event_bytes) != manifest.events_sha256:
        raise DatasetVerificationError("events.jsonl hash mismatch")
    if sha256_bytes(refusal_bytes) != manifest.refusals_sha256:
        raise DatasetVerificationError("refusals.jsonl hash mismatch")
    events = _load_canonical_jsonl(
        event_bytes, name=EVENTS_FILENAME, record_type=CanonicalSourceEvent
    )
    refusals = _load_canonical_jsonl(
        refusal_bytes, name=REFUSALS_FILENAME, record_type=NormalizationRefusal
    )
    if len(events) != manifest.event_count or len(refusals) != manifest.refusal_count:
        raise DatasetVerificationError("parsed JSONL counts do not match manifest")

    provenance = NormalizationProvenance(
        normalizer_config_sha256=manifest.normalizer_config_sha256,
        normalizer_code_sha256=manifest.normalizer_code_sha256,
        evidence_epoch_id=manifest.evidence_epoch_id,
        build_recipe_id=manifest.build_recipe_id,
        build_recipe_sha256=manifest.build_recipe_sha256,
        producing_commit=manifest.producing_commit,
    )
    result = NormalizationResult(
        snapshot=snapshot,
        events=events,
        refusals=refusals,
        provenance=provenance,
    )
    if result.result_sha256 != manifest.normalization_result_sha256:
        raise DatasetVerificationError("normalization result hash mismatch")
    return _normalized_dataset(root_path, manifest, snapshot, events, refusals)
