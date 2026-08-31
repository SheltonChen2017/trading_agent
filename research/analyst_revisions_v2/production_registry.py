"""Git-anchored production registration for ARV2 reference artifacts.

Structural loaders deliberately accept synthetic local fixtures.  They do not
thereby grant production authority.  This module is the shared, narrow gate
that binds an exact artifact to an independently reviewed commit and to a
fixed committed registry before a production consumer may use it.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

from .canonical import (
    CanonicalEvidenceError,
    parse_utc_timestamp,
    require_canonical_json_bytes,
    require_exact_keys,
    require_git_object,
    require_identifier,
    require_sha256,
    require_text,
    sha256_bytes,
)
from .dataset import (
    DatasetVerificationError,
    git_commit_is_ancestor,
    read_git_bytes,
    read_git_text,
)


_REGISTRY_KEYS = frozenset({"schema", "entries"})
_ENTRY_KEYS = frozenset(
    {
        "artifact_id",
        "artifact_sha256",
        "artifact_path",
        "review_commit",
        "reviewed_by",
        "reviewed_at",
    }
)


class ProductionRegistryError(CanonicalEvidenceError):
    """A reference artifact lacks an exact independent production anchor."""


@dataclasses.dataclass(frozen=True)
class ProductionRegistryEntry:
    artifact_id: str
    artifact_sha256: str
    artifact_path: str
    review_commit: str
    reviewed_by: str
    reviewed_at: str

    def __post_init__(self) -> None:
        require_identifier(self.artifact_id, "artifact_id")
        require_sha256(self.artifact_sha256, "artifact_sha256")
        require_text(self.artifact_path, "artifact_path", maximum_length=512)
        path = Path(self.artifact_path)
        if "\\" in self.artifact_path or path.is_absolute():
            raise ProductionRegistryError(
                "artifact_path must be a repository-relative POSIX path"
            )
        if any(part in {"", ".", ".."} for part in path.parts):
            raise ProductionRegistryError(
                "artifact_path must not contain empty or traversal components"
            )
        require_git_object(self.review_commit, "review_commit")
        require_text(self.reviewed_by, "reviewed_by")
        parse_utc_timestamp(self.reviewed_at, "reviewed_at")

    @classmethod
    def from_record(cls, record: object) -> "ProductionRegistryEntry":
        if not isinstance(record, dict):
            raise ProductionRegistryError("production registry entry must be an object")
        require_exact_keys(record, _ENTRY_KEYS, "production registry entry")
        return cls(**record)


def _git_text(root: Path, *arguments: str) -> str:
    try:
        return read_git_text(root, arguments)
    except (DatasetVerificationError, OSError, UnicodeError) as exc:
        raise ProductionRegistryError(
            "production registry Git verification could not run"
        ) from exc


def _git_bytes(root: Path, *arguments: str) -> bytes:
    try:
        return read_git_bytes(root, arguments)
    except (DatasetVerificationError, OSError, UnicodeError) as exc:
        raise ProductionRegistryError(
            "production registry Git verification could not run"
        ) from exc


def require_production_registry_entry(
    *,
    artifact_path: Path,
    artifact_id: str,
    artifact_sha256: str,
    registry_path: Path,
    registry_schema: str,
    artifact_kind: str,
) -> ProductionRegistryEntry:
    """Authenticate one exact artifact against a committed review registry.

    Empty registries fail before any Git command.  This is the checked-in
    zero-access state for ARV2 reference data and prevents a caller-created
    artifact from promoting itself merely by carrying plausible metadata.
    """
    require_identifier(artifact_id, "artifact_id")
    require_sha256(artifact_sha256, "artifact_sha256")
    require_identifier(registry_schema, "registry_schema")
    require_text(artifact_kind, "artifact_kind")
    registry_candidate = registry_path
    if registry_candidate.is_symlink():
        raise ProductionRegistryError(
            f"{artifact_kind} production registry must not be a symlink"
        )
    try:
        registry_resolved = registry_candidate.resolve(strict=True)
    except OSError as exc:
        raise ProductionRegistryError(
            f"{artifact_kind} production registry is absent"
        ) from exc
    if not registry_resolved.is_file() or registry_resolved.is_symlink():
        raise ProductionRegistryError(
            f"{artifact_kind} production registry must be a regular file"
        )
    try:
        registry_payload = registry_resolved.read_bytes()
        raw = require_canonical_json_bytes(
            registry_payload, f"{artifact_kind} production registry"
        )
    except (OSError, CanonicalEvidenceError) as exc:
        raise ProductionRegistryError(
            f"{artifact_kind} production registry is noncanonical"
        ) from exc
    if not isinstance(raw, dict):
        raise ProductionRegistryError(
            f"{artifact_kind} production registry must be an object"
        )
    require_exact_keys(raw, _REGISTRY_KEYS, f"{artifact_kind} production registry")
    if raw["schema"] != registry_schema:
        raise ProductionRegistryError(
            f"{artifact_kind} production registry schema is unsupported"
        )
    entries_raw = raw["entries"]
    if not isinstance(entries_raw, list):
        raise ProductionRegistryError(
            f"{artifact_kind} production registry entries must be an array"
        )
    entries = tuple(ProductionRegistryEntry.from_record(item) for item in entries_raw)
    entry_ids = tuple(entry.artifact_id for entry in entries)
    if entry_ids != tuple(sorted(set(entry_ids))):
        raise ProductionRegistryError(
            f"{artifact_kind} production registry IDs must be unique and sorted"
        )
    matches = tuple(entry for entry in entries if entry.artifact_id == artifact_id)
    if len(matches) != 1:
        raise ProductionRegistryError(
            f"{artifact_kind} has no unique production registration"
        )
    entry = matches[0]

    artifact_candidate = artifact_path
    if artifact_candidate.is_symlink():
        raise ProductionRegistryError(
            f"registered {artifact_kind} artifact must not be a symlink"
        )
    try:
        artifact_resolved = artifact_candidate.resolve(strict=True)
    except OSError as exc:
        raise ProductionRegistryError(
            f"registered {artifact_kind} artifact is absent"
        ) from exc
    if not artifact_resolved.is_file() or artifact_resolved.is_symlink():
        raise ProductionRegistryError(
            f"registered {artifact_kind} artifact must be a regular file"
        )
    artifact_payload = artifact_resolved.read_bytes()
    if sha256_bytes(artifact_payload) != artifact_sha256:
        raise ProductionRegistryError(
            f"registered {artifact_kind} artifact bytes changed"
        )

    registry_root = Path(
        _git_text(registry_resolved.parent, "rev-parse", "--show-toplevel").strip()
    ).resolve(strict=True)
    artifact_root = Path(
        _git_text(artifact_resolved.parent, "rev-parse", "--show-toplevel").strip()
    ).resolve(strict=True)
    if registry_root != artifact_root:
        raise ProductionRegistryError(
            f"{artifact_kind} artifact and production registry are not in one repository"
        )
    try:
        registry_relative = registry_resolved.relative_to(registry_root).as_posix()
        artifact_relative = artifact_resolved.relative_to(registry_root).as_posix()
    except ValueError as exc:
        raise ProductionRegistryError(
            f"{artifact_kind} production paths escaped the repository"
        ) from exc
    if entry.artifact_path != artifact_relative or (
        entry.artifact_sha256 != artifact_sha256
    ):
        raise ProductionRegistryError(
            f"{artifact_kind} production registration does not match the artifact"
        )

    status = _git_text(
        registry_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        registry_relative,
        artifact_relative,
    )
    if status:
        raise ProductionRegistryError(
            f"{artifact_kind} artifact and registry must be committed and clean"
        )
    _git_text(registry_root, "ls-files", "--error-unmatch", "--", registry_relative)
    _git_text(registry_root, "ls-files", "--error-unmatch", "--", artifact_relative)
    committed_registry = _git_bytes(
        registry_root, "show", f"HEAD:{registry_relative}"
    )
    if committed_registry != registry_payload:
        raise ProductionRegistryError(
            f"{artifact_kind} working registry differs from committed bytes"
        )
    _git_text(registry_root, "cat-file", "-e", f"{entry.review_commit}^{{commit}}")
    try:
        review_is_ancestor = git_commit_is_ancestor(
            registry_root, entry.review_commit, "HEAD"
        )
    except DatasetVerificationError as exc:
        raise ProductionRegistryError(
            f"{artifact_kind} independent review ancestry cannot be verified"
        ) from exc
    if not review_is_ancestor:
        raise ProductionRegistryError(
            f"{artifact_kind} review commit is not an ancestor of HEAD"
        )
    reviewed_artifact = _git_bytes(
        registry_root, "show", f"{entry.review_commit}:{artifact_relative}"
    )
    if sha256_bytes(reviewed_artifact) != artifact_sha256:
        raise ProductionRegistryError(
            f"{artifact_kind} differs from the independently reviewed blob"
        )
    if (
        registry_resolved.read_bytes() != registry_payload
        or artifact_resolved.read_bytes() != artifact_payload
    ):
        raise ProductionRegistryError(
            f"{artifact_kind} artifact or registry changed during authentication"
        )
    # The entry's review_commit authenticates the artifact blob, but it cannot
    # authenticate the registry entry that names that same commit: embedding a
    # commit's own hash in its contents is circular.  Until a separately pinned,
    # non-self-referential approval receipt exists, a checked-in entry must stay
    # structural and fail closed rather than promote itself to production.
    raise ProductionRegistryError(
        f"{artifact_kind} production registration approval authority is absent; "
        "the committed registry remains zero-access"
    )
