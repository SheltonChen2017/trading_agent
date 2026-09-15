"""Owner-only immutable publication for non-authorizing firm candidates."""
from __future__ import annotations

import dataclasses
import os
import secrets
import shutil
import stat
import threading
import weakref
from pathlib import Path

from research.analyst_revisions_v2.canonical import (
    canonical_json_bytes,
    sha256_bytes,
)
from research.analyst_revisions_v2_qc import (
    firm_ontology_candidate_builder as _builder,
)
from research.analyst_revisions_v2_qc import (
    physical_firm_ontology_review_packet as _publication,
)
from research.analyst_revisions_v2_qc.firm_ontology_candidate_builder import (
    FirmOntologyCandidateBundle,
)


ARCHIVE_SCHEMA = "arv2-physical-firm-ontology-candidate-archive-v1"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_DIGEST_FILENAME = "manifest.sha256"
OWNER_ADJUDICATION_FILENAME = "owner-adjudication.reviewed.jsonl"
ONTOLOGY_FILENAME = "firm-ontology.candidate.json"
AVAILABILITY_FILENAME = "firm-availability.candidate.json"
AVAILABILITY_REVIEW_FILENAME = "firm-availability-review.candidate.json"
REGISTRY_CANDIDATE_FILENAME = "firm-ontology-registry-entry.candidate.json"
COVERAGE_FILENAME = "coverage-diagnostics.json"
MAX_CANDIDATE_FILE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024

_PATH_TYPE = type(Path())
_PINNED_BUNDLE_TYPE = FirmOntologyCandidateBundle
_PINNED_BUNDLE_REQUIRE = _builder.require_firm_ontology_candidate_bundle
_PINNED_PUBLISH_STAGE = _publication._publish_stage
_PINNED_ROLLBACK_STAGE = _publication._rollback_published_stage
_PINNED_CANONICAL_JSON_BYTES = canonical_json_bytes
_PINNED_SHA256_BYTES = sha256_bytes


class FirmOntologyCandidatePublicationError(ValueError):
    """The private immutable candidate publication did not complete."""


class FirmOntologyCandidatePublicationAmbiguityError(
    FirmOntologyCandidatePublicationError
):
    """Publication durability is uncertain; private residue is preserved."""


@dataclasses.dataclass(frozen=True, slots=True)
class CandidateFileDescriptor:
    role: str
    filename: str
    byte_count: int
    content_sha256: str

    def to_record(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True)
class PhysicalFirmOntologyCandidateArchive:
    schema: str
    archive_id: str
    archive_sha256: str
    archive_path: Path
    bundle_id: str
    bundle_sha256: str
    packet_id: str
    packet_sha256: str
    owner_adjudication_sha256: str
    firm_count: int
    ontology_entry_count: int
    files: tuple[CandidateFileDescriptor, ...]
    independently_reviewed: bool
    production_authority: bool
    provider_access: bool
    quantconnect_access: bool
    outcome_access: bool
    deployment: bool
    orders: bool
    trading: bool


@dataclasses.dataclass(frozen=True, slots=True)
class _Identity:
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int
    mode: int
    owner: int
    links: int


_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[PhysicalFirmOntologyCandidateArchive],
        tuple[object, ...],
        _Identity,
        tuple[tuple[str, _Identity], ...],
        int,
    ],
] = {}
_AUTHORITY_LOCK = threading.RLock()
_AUTHORITY_PID = os.getpid()


def _reset_authorities_after_fork() -> None:
    """Discard inherited authorities and replace a potentially orphaned lock."""

    global _AUTHORITIES, _AUTHORITY_LOCK, _AUTHORITY_PID
    _AUTHORITIES = {}
    _AUTHORITY_LOCK = threading.RLock()
    _AUTHORITY_PID = os.getpid()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_authorities_after_fork)


def _forget(identity: int, reference: object) -> None:
    with _AUTHORITY_LOCK:
        current = _AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _AUTHORITIES.pop(identity, None)


def _fingerprint(value: PhysicalFirmOntologyCandidateArchive) -> tuple[object, ...]:
    return tuple(getattr(value, field.name) for field in dataclasses.fields(value))


def _dependencies_current() -> bool:
    return (
        _builder.FirmOntologyCandidateBundle is _PINNED_BUNDLE_TYPE
        and _builder.require_firm_ontology_candidate_bundle is _PINNED_BUNDLE_REQUIRE
        and _publication._publish_stage is _PINNED_PUBLISH_STAGE
        and _publication._rollback_published_stage is _PINNED_ROLLBACK_STAGE
        and canonical_json_bytes is _PINNED_CANONICAL_JSON_BYTES
        and sha256_bytes is _PINNED_SHA256_BYTES
    )


def _identity(path: Path, *, directory: bool) -> _Identity:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise FirmOntologyCandidatePublicationError(
            "candidate archive entry is unavailable"
        ) from exc
    expected_kind = stat.S_ISDIR if directory else stat.S_ISREG
    expected_mode = 0o700 if directory else 0o600
    if (
        not expected_kind(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != expected_mode
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
        or (not directory and metadata.st_nlink != 1)
    ):
        raise FirmOntologyCandidatePublicationError(
            "candidate archive entries must remain exact owner-only objects"
        )
    return _Identity(
        device=metadata.st_dev,
        inode=metadata.st_ino,
        size=metadata.st_size,
        modified_ns=metadata.st_mtime_ns,
        changed_ns=metadata.st_ctime_ns,
        mode=metadata.st_mode,
        owner=metadata.st_uid,
        links=metadata.st_nlink,
    )


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise FirmOntologyCandidatePublicationError(
                "candidate archive write did not progress"
            )
        offset += written


def _write_private(path: Path, payload: bytes) -> _Identity:
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_CANDIDATE_FILE_BYTES:
        raise FirmOntologyCandidatePublicationError(
            "candidate output exceeds its fixed nonempty byte bound"
        )
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise FirmOntologyCandidatePublicationError(
            "candidate output could not be created without replacement"
        ) from exc
    try:
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    identity = _identity(path, directory=False)
    if identity.size != len(payload):
        raise FirmOntologyCandidatePublicationError(
            "candidate output size changed during publication"
        )
    return identity


def _read_exact(path: Path, expected: _Identity, maximum: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise FirmOntologyCandidatePublicationError(
            "candidate archive entry is unavailable"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if before.st_size > maximum:
            raise FirmOntologyCandidatePublicationError(
                "candidate archive entry exceeds its byte bound"
            )
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise FirmOntologyCandidatePublicationError(
                    "candidate archive entry ended early"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise FirmOntologyCandidatePublicationError(
                "candidate archive entry grew while read"
            )
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    observed = _Identity(
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_mode,
        after.st_uid,
        after.st_nlink,
    )
    if observed != expected or _identity(path, directory=False) != expected:
        raise FirmOntologyCandidatePublicationError(
            "candidate archive entry identity changed"
        )
    return b"".join(chunks)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        os.fsync(descriptor)
    except OSError as exc:
        raise FirmOntologyCandidatePublicationError(
            "candidate archive directory could not be synchronized"
        ) from exc
    finally:
        try:
            os.close(descriptor)
        except (OSError, UnboundLocalError):
            pass


def _create_private_output_root(path: Path) -> Path:
    if (
        type(path) is not _PATH_TYPE
        or not path.is_absolute()
        or ".." in path.parts
        or path.name in {"", ".", ".."}
    ):
        raise FirmOntologyCandidatePublicationError(
            "candidate output root must be a fresh exact absolute Path"
        )
    if path.exists() or path.is_symlink():
        raise FirmOntologyCandidatePublicationError(
            "candidate output root already exists; overwrite is forbidden"
        )
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as exc:
        raise FirmOntologyCandidatePublicationError(
            "candidate output parent is unavailable"
        ) from exc
    if parent != path.parent:
        raise FirmOntologyCandidatePublicationError(
            "candidate output parent must not traverse a symlink"
        )
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        parent_fd = os.open(parent, flags)
        os.mkdir(path.name, 0o700, dir_fd=parent_fd)
        root_fd = os.open(path.name, flags, dir_fd=parent_fd)
        try:
            os.fchmod(root_fd, 0o700)
            os.fsync(root_fd)
        finally:
            os.close(root_fd)
        os.fsync(parent_fd)
    except OSError as exc:
        raise FirmOntologyCandidatePublicationError(
            "candidate private output root could not be created durably"
        ) from exc
    finally:
        try:
            os.close(parent_fd)
        except (OSError, UnboundLocalError):
            pass
    _identity(path, directory=True)
    return path


def _file_payloads(bundle: FirmOntologyCandidateBundle) -> tuple[tuple[str, str, bytes], ...]:
    return (
        (
            "owner_adjudication",
            OWNER_ADJUDICATION_FILENAME,
            bundle.owner_adjudication_bytes,
        ),
        ("firm_ontology", ONTOLOGY_FILENAME, bundle.ontology_bytes),
        ("firm_availability", AVAILABILITY_FILENAME, bundle.availability_bytes),
        (
            "firm_availability_review_candidate",
            AVAILABILITY_REVIEW_FILENAME,
            bundle.availability_review_candidate_bytes,
        ),
        (
            "firm_ontology_registry_entry_candidate",
            REGISTRY_CANDIDATE_FILENAME,
            bundle.registry_candidate_bytes,
        ),
        ("coverage_diagnostics", COVERAGE_FILENAME, bundle.coverage_diagnostic_bytes),
    )


def _manifest_seed(
    bundle: FirmOntologyCandidateBundle,
    files: tuple[CandidateFileDescriptor, ...],
) -> dict[str, object]:
    return {
        "schema": ARCHIVE_SCHEMA,
        "bundle_id": bundle.bundle_id,
        "bundle_sha256": bundle.bundle_sha256,
        "packet_id": bundle.packet_id,
        "packet_sha256": bundle.packet_sha256,
        "owner_adjudication_sha256": bundle.owner_adjudication_sha256,
        "firm_count": bundle.firm_count,
        "ontology_entry_count": bundle.ontology_entry_count,
        "files": [item.to_record() for item in files],
        "storage": {
            "owner_only": True,
            "immutable_no_replace": True,
            "content_addressed": True,
            "provider_derived_firm_names_and_labels_present": True,
        },
        "capabilities": {
            "independently_reviewed": False,
            "production_authority": False,
            "provider_access": False,
            "quantconnect_access": False,
            "outcome_access": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        },
    }


def _mint(
    *,
    archive_path: Path,
    archive_sha256: str,
    bundle: FirmOntologyCandidateBundle,
    files: tuple[CandidateFileDescriptor, ...],
) -> PhysicalFirmOntologyCandidateArchive:
    value = PhysicalFirmOntologyCandidateArchive(
        schema=ARCHIVE_SCHEMA,
        archive_id=bundle.bundle_id,
        archive_sha256=archive_sha256,
        archive_path=archive_path,
        bundle_id=bundle.bundle_id,
        bundle_sha256=bundle.bundle_sha256,
        packet_id=bundle.packet_id,
        packet_sha256=bundle.packet_sha256,
        owner_adjudication_sha256=bundle.owner_adjudication_sha256,
        firm_count=bundle.firm_count,
        ontology_entry_count=bundle.ontology_entry_count,
        files=files,
        independently_reviewed=False,
        production_authority=False,
        provider_access=False,
        quantconnect_access=False,
        outcome_access=False,
        deployment=False,
        orders=False,
        trading=False,
    )
    root_identity = _identity(archive_path, directory=True)
    names = (MANIFEST_FILENAME, MANIFEST_DIGEST_FILENAME) + tuple(
        item.filename for item in files
    )
    file_identities = tuple(
        (name, _identity(archive_path / name, directory=False))
        for name in sorted(names)
    )
    identity = id(value)
    reference = weakref.ref(value, lambda ref, key=identity: _forget(key, ref))
    with _AUTHORITY_LOCK:
        _AUTHORITIES[identity] = (
            reference,
            _fingerprint(value),
            root_identity,
            file_identities,
            os.getpid(),
        )
    return value


def _publish(
    *,
    candidate_bundle: FirmOntologyCandidateBundle,
    output_root: Path,
    publish_stage,
    rollback_stage,
) -> PhysicalFirmOntologyCandidateArchive:
    if not _dependencies_current():
        raise FirmOntologyCandidatePublicationError(
            "candidate publisher dependency binding changed"
        )
    if type(candidate_bundle) is not _PINNED_BUNDLE_TYPE:
        raise FirmOntologyCandidatePublicationError(
            "candidate publisher requires exact builder authority"
        )
    bundle = _PINNED_BUNDLE_REQUIRE(candidate_bundle)
    root = _create_private_output_root(output_root)
    stage = root / f".firm-candidate-stage-{secrets.token_hex(16)}"
    final = root / bundle.bundle_id
    published = False
    preserve = False
    try:
        stage.mkdir(mode=0o700)
        stage.chmod(0o700)
        _identity(stage, directory=True)
        files: list[CandidateFileDescriptor] = []
        total_bytes = 0
        for role, filename, payload in _file_payloads(bundle):
            total_bytes += len(payload)
            if total_bytes > MAX_ARCHIVE_BYTES:
                raise FirmOntologyCandidatePublicationError(
                    "candidate archive exceeds its total byte bound"
                )
            _write_private(stage / filename, payload)
            files.append(
                CandidateFileDescriptor(
                    role=role,
                    filename=filename,
                    byte_count=len(payload),
                    content_sha256=sha256_bytes(payload),
                )
            )
        descriptors = tuple(files)
        seed = _manifest_seed(bundle, descriptors)
        archive_sha = sha256_bytes(canonical_json_bytes(seed))
        manifest = canonical_json_bytes(
            {
                "schema": ARCHIVE_SCHEMA,
                "archive_id": bundle.bundle_id,
                "archive_sha256": archive_sha,
                "archive_seed": seed,
            }
        )
        total_bytes += len(manifest) + 65
        if total_bytes > MAX_ARCHIVE_BYTES:
            raise FirmOntologyCandidatePublicationError(
                "candidate archive exceeds its total byte bound"
            )
        _write_private(stage / MANIFEST_FILENAME, manifest)
        _write_private(
            stage / MANIFEST_DIGEST_FILENAME,
            (sha256_bytes(manifest) + "\n").encode("ascii"),
        )
        _fsync_directory(stage)
        _PINNED_BUNDLE_REQUIRE(bundle)
        try:
            publish_stage(stage, final)
        except _publication.PhysicalFirmOntologyReviewPacketPublicationAmbiguityError as exc:
            preserve = True
            raise FirmOntologyCandidatePublicationAmbiguityError(
                "candidate publication durability is ambiguous; private residue preserved"
            ) from exc
        except _publication.PhysicalFirmOntologyReviewPacketError as exc:
            raise FirmOntologyCandidatePublicationError(
                "candidate publication failed without replacement"
            ) from exc
        published = True
        try:
            archive = _mint(
                archive_path=final,
                archive_sha256=archive_sha,
                bundle=bundle,
                files=descriptors,
            )
            return require_physical_firm_ontology_candidate_archive(archive)
        except Exception:
            try:
                rollback_stage(stage, final)
            except _publication.PhysicalFirmOntologyReviewPacketPublicationAmbiguityError as exc:
                preserve = True
                raise FirmOntologyCandidatePublicationAmbiguityError(
                    "candidate late rollback is ambiguous; private residue preserved"
                ) from exc
            published = False
            raise
    finally:
        if not published and not preserve and stage.exists():
            shutil.rmtree(stage)


def publish_firm_ontology_candidate_bundle(
    *,
    candidate_bundle: FirmOntologyCandidateBundle,
    output_root: Path,
) -> PhysicalFirmOntologyCandidateArchive:
    """Publish a new owner-only archive; existing roots are never reused."""

    return _publish(
        candidate_bundle=candidate_bundle,
        output_root=output_root,
        publish_stage=_PINNED_PUBLISH_STAGE,
        rollback_stage=_PINNED_ROLLBACK_STAGE,
    )


def _publish_firm_ontology_candidate_bundle_for_test(
    *,
    candidate_bundle: FirmOntologyCandidateBundle,
    output_root: Path,
    publish_stage=None,
    rollback_stage=None,
) -> PhysicalFirmOntologyCandidateArchive:
    return _publish(
        candidate_bundle=candidate_bundle,
        output_root=output_root,
        publish_stage=(
            _PINNED_PUBLISH_STAGE if publish_stage is None else publish_stage
        ),
        rollback_stage=(
            _PINNED_ROLLBACK_STAGE if rollback_stage is None else rollback_stage
        ),
    )


def require_physical_firm_ontology_candidate_archive(
    value: PhysicalFirmOntologyCandidateArchive,
) -> PhysicalFirmOntologyCandidateArchive:
    """Reauthenticate every published byte and the non-authorizing fields."""

    if not _dependencies_current():
        raise FirmOntologyCandidatePublicationError(
            "candidate publisher dependency binding changed"
        )
    if type(value) is not PhysicalFirmOntologyCandidateArchive:
        raise FirmOntologyCandidatePublicationError(
            "candidate archive requires the exact published type"
        )
    current_pid = os.getpid()
    if current_pid != _AUTHORITY_PID:
        raise FirmOntologyCandidatePublicationError(
            "candidate archive authority belongs to another process"
        )
    with _AUTHORITY_LOCK:
        authority = _AUTHORITIES.get(id(value))
    if (
        authority is None
        or authority[0]() is not value
        or authority[1] != _fingerprint(value)
        or authority[2] != _identity(value.archive_path, directory=True)
        or authority[4] != current_pid
    ):
        raise FirmOntologyCandidatePublicationError(
            "candidate archive is not current publisher authority"
        )
    if (
        value.schema != ARCHIVE_SCHEMA
        or value.archive_id != value.bundle_id
        or value.firm_count != 74
        or type(value.files) is not tuple
        or tuple(item.role for item in value.files)
        != (
            "owner_adjudication",
            "firm_ontology",
            "firm_availability",
            "firm_availability_review_candidate",
            "firm_ontology_registry_entry_candidate",
            "coverage_diagnostics",
        )
        or any(type(item) is not CandidateFileDescriptor for item in value.files)
        or any(
            type(getattr(value, name)) is not bool
            or getattr(value, name) is not False
            for name in (
                "independently_reviewed",
                "production_authority",
                "provider_access",
                "quantconnect_access",
                "outcome_access",
                "deployment",
                "orders",
                "trading",
            )
        )
    ):
        raise FirmOntologyCandidatePublicationError(
            "candidate archive authority fields changed"
        )
    identities = dict(authority[3])
    expected_names = {
        MANIFEST_FILENAME,
        MANIFEST_DIGEST_FILENAME,
        *(item.filename for item in value.files),
    }
    try:
        actual_names = set(os.listdir(value.archive_path))
    except OSError as exc:
        raise FirmOntologyCandidatePublicationError(
            "candidate archive inventory is unavailable"
        ) from exc
    if actual_names != expected_names or set(identities) != expected_names:
        raise FirmOntologyCandidatePublicationError(
            "candidate archive inventory changed"
        )
    for descriptor in value.files:
        payload = _read_exact(
            value.archive_path / descriptor.filename,
            identities[descriptor.filename],
            MAX_CANDIDATE_FILE_BYTES,
        )
        if (
            len(payload) != descriptor.byte_count
            or sha256_bytes(payload) != descriptor.content_sha256
        ):
            raise FirmOntologyCandidatePublicationError(
                "candidate archive file content changed"
            )
    manifest = _read_exact(
        value.archive_path / MANIFEST_FILENAME,
        identities[MANIFEST_FILENAME],
        MAX_CANDIDATE_FILE_BYTES,
    )
    digest = _read_exact(
        value.archive_path / MANIFEST_DIGEST_FILENAME,
        identities[MANIFEST_DIGEST_FILENAME],
        65,
    )
    seed = {
        "schema": ARCHIVE_SCHEMA,
        "bundle_id": value.bundle_id,
        "bundle_sha256": value.bundle_sha256,
        "packet_id": value.packet_id,
        "packet_sha256": value.packet_sha256,
        "owner_adjudication_sha256": value.owner_adjudication_sha256,
        "firm_count": value.firm_count,
        "ontology_entry_count": value.ontology_entry_count,
        "files": [item.to_record() for item in value.files],
        "storage": {
            "owner_only": True,
            "immutable_no_replace": True,
            "content_addressed": True,
            "provider_derived_firm_names_and_labels_present": True,
        },
        "capabilities": {
            "independently_reviewed": False,
            "production_authority": False,
            "provider_access": False,
            "quantconnect_access": False,
            "outcome_access": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        },
    }
    expected_manifest = canonical_json_bytes(
        {
            "schema": ARCHIVE_SCHEMA,
            "archive_id": value.archive_id,
            "archive_sha256": value.archive_sha256,
            "archive_seed": seed,
        }
    )
    if (
        sha256_bytes(canonical_json_bytes(seed)) != value.archive_sha256
        or manifest != expected_manifest
        or digest != (sha256_bytes(manifest) + "\n").encode("ascii")
    ):
        raise FirmOntologyCandidatePublicationError(
            "candidate archive manifest does not authenticate"
        )
    return value


__all__ = [
    "ARCHIVE_SCHEMA",
    "AVAILABILITY_FILENAME",
    "AVAILABILITY_REVIEW_FILENAME",
    "COVERAGE_FILENAME",
    "CandidateFileDescriptor",
    "FirmOntologyCandidatePublicationAmbiguityError",
    "FirmOntologyCandidatePublicationError",
    "MANIFEST_DIGEST_FILENAME",
    "MANIFEST_FILENAME",
    "ONTOLOGY_FILENAME",
    "OWNER_ADJUDICATION_FILENAME",
    "PhysicalFirmOntologyCandidateArchive",
    "REGISTRY_CANDIDATE_FILENAME",
    "publish_firm_ontology_candidate_bundle",
    "require_physical_firm_ontology_candidate_archive",
]
