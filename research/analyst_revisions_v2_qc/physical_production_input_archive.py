"""Disk-backed, byte-exact C2 evidence and pre-outcome batch archive.

The original C2 objects remain the small-fixture oracle.  They intentionally
retain the complete C1 pair, evidence tuple, admission censuses, and normalized
rows.  A real Massive capture is too large for that object graph.  This module
derives the same semantic authority, package, comparison report, and two batch
hashes while keeping source rows, evidence rows, and admissions on private
disk.  Only one source/evidence/admission pair is live while deriving C2.

This is an inert pre-outcome boundary.  It neither reads providers nor grants
formal-run authority.  A caller must separately bind the resulting exact
package and authority hashes to the independently signed review pin before a
formal run may consume them.  The explicitly named test-fixture entry point is
the only route that accepts the legacy in-memory authority.
"""
from __future__ import annotations

import dataclasses
import ctypes
import errno
import hashlib
import os
import secrets
import sqlite3
import stat
import sys
import threading
import weakref
from collections.abc import Callable, Iterable, Iterator, Mapping
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any

from research.analyst_revisions_v2 import production_input_pipeline as _c2
from research.analyst_revisions_v2.accepted_risk_input_pair import (
    AcceptedRiskSourceRow,
    CaptureRowLocator,
    InputView,
    MassiveSourceRole,
)
from research.analyst_revisions_v2.canonical import (
    CanonicalEvidenceError,
    canonical_json_bytes,
    decode_utf8,
    require_identifier,
    require_int,
    require_sha256,
    sha256_bytes,
    strict_json_loads,
)
from research.analyst_revisions_v2.production_evidence_acquisition import (
    PACKAGE_SCHEMA,
    ROW_PROJECTION_SCHEMA,
    SOURCE_PROJECTION_SCHEMA,
)
from research.analyst_revisions_v2.production_input_pipeline import (
    CommonEventIdentityEvidence,
    ComparisonDimension,
    DataQualityEvidence,
    EvidenceSourceBinding,
    EvidenceSourceKind,
    FirmOntologyEvidence,
    NormalizedPreOutcomeRow,
    PreopenControlEvidence,
    ProductionEvidenceAuthority,
    ProductionRowEvidence,
    SectorClassificationEvidence,
    SecurityIdentityEvidence,
    SignalArm,
)
from research.analyst_revisions_v2_qc import physical_accepted_risk_archive as _c1_disk
from research.analyst_revisions_v2_qc.formal_run_protocol import (
    AcceptedRiskPairBinding,
    FormalRunProtocolError,
    require_accepted_risk_pair_binding,
)


ARCHIVE_SCHEMA = "arv2-physical-production-input-archive-v1"
ARCHIVE_MANIFEST = "manifest.json"
ARCHIVE_MANIFEST_DIGEST = "manifest.sha256"
EVIDENCE_ROWS = "evidence-rows.jsonl"
EVIDENCE_PACKAGE = "evidence-package.json"
COMPARISON_REPORT = "comparison-report.json"
CURRENT_ADMISSIONS = "current-admissions.jsonl"
CURRENT_NORMALIZED = "current-normalized.jsonl"
CENSORED_ADMISSIONS = "censored-admissions.jsonl"
CENSORED_NORMALIZED = "censored-normalized.jsonl"
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_RECORD_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_FILE_BYTES = 8 * 1024 * 1024 * 1024
MAX_SOURCE_ROWS = 20_000_000
MAX_EVIDENCE_ROWS = 20_000_000
MAX_SQLITE_BYTES = 16 * 1024 * 1024 * 1024
SPOOL_BOUND_CHECK_INTERVAL = 256
IO_CHUNK_BYTES = 1024 * 1024

_LINEAGE_SCAN_SQL = (
    "SELECT namespace, identifier, valid_from, valid_to, identity_value "
    "FROM lineage ORDER BY namespace, identifier, valid_from, "
    "valid_to, identity_value"
)

_COMPONENT_NAMES = (
    "security",
    "firm",
    "common_event",
    "sector",
    "control",
    "q_data",
)
_SOURCE_ORDER = tuple(EvidenceSourceKind)
_ARM_ORDER = (SignalArm.CURRENT_VINTAGE, SignalArm.CONSERVATIVE_CENSORED)
_ARM_TO_VIEW = {
    SignalArm.CURRENT_VINTAGE: InputView.CURRENT_ROW,
    SignalArm.CONSERVATIVE_CENSORED: InputView.CONSERVATIVE_CENSORED,
}
_ARM_TO_LABEL = {arm: _c2._ARM_TO_LABEL[arm] for arm in _ARM_ORDER}

_PINNED_REQUIRE_STATIC_CONTRACT = _c2._require_static_contract
_PINNED_ADMIT_SOURCE_ROW = _c2._admit_source_row
_PINNED_MAPPING_SIGNATURE = _c2._mapping_signature
_PINNED_SIGNAL_SIGNATURE = _c2._signal_signature
_PINNED_ACCEPTED_RISK_BINDING_TYPE = AcceptedRiskPairBinding
_PINNED_REQUIRE_ACCEPTED_RISK_BINDING = require_accepted_risk_pair_binding
_PINNED_C1_ARCHIVE_TYPE = _c1_disk.PhysicalAcceptedRiskArchive
_PINNED_REQUIRE_C1_ARCHIVE = _c1_disk.require_physical_accepted_risk_archive
_PINNED_ITER_C1_ROWS = _c1_disk.iter_physical_accepted_risk_rows
_PINNED_C1_MASSIVE_MODULE = _c1_disk._massive
_PINNED_PRODUCTION_C1_TRANSPORT = _c1_disk._massive.PRODUCTION_TRANSPORT
_PINNED_REPOSITORY_ARTIFACTS_ROOT = (
    _c1_disk._massive.REPOSITORY_ARTIFACTS_ROOT
)
_PINNED_SOURCE_ROW_TYPE = AcceptedRiskSourceRow
_PINNED_SOURCE_ROW_POST_INIT = AcceptedRiskSourceRow.__post_init__
_PINNED_LOCATOR_TYPE = CaptureRowLocator
_PINNED_LOCATOR_TO_RECORD = CaptureRowLocator.to_record
_PINNED_SOURCE_BINDING_TYPE = EvidenceSourceBinding
_PINNED_SOURCE_BINDING_POST_INIT = EvidenceSourceBinding.__post_init__
_PINNED_SOURCE_BINDING_TO_RECORD = EvidenceSourceBinding.to_record
_PINNED_EVIDENCE_ROW_TYPE = ProductionRowEvidence
_PINNED_EVIDENCE_ROW_POST_INIT = ProductionRowEvidence.__post_init__
_PINNED_EVIDENCE_ROW_TO_RECORD = ProductionRowEvidence.to_record
_PINNED_COMPONENT_TYPES = (
    SecurityIdentityEvidence,
    FirmOntologyEvidence,
    CommonEventIdentityEvidence,
    SectorClassificationEvidence,
    PreopenControlEvidence,
    DataQualityEvidence,
)
_PINNED_COMPONENT_POST_INITS = tuple(
    component_type.__post_init__ for component_type in _PINNED_COMPONENT_TYPES
)
_PINNED_COMPONENT_TO_RECORDS = tuple(
    component_type.to_record for component_type in _PINNED_COMPONENT_TYPES
)


def _load_native_rename_noreplace() -> tuple[object | None, int | None]:
    try:
        library = ctypes.CDLL(None, use_errno=True)
        if sys.platform == "darwin":
            function = library.renameatx_np
            flag = 0x00000004  # RENAME_EXCL
        elif sys.platform.startswith("linux"):
            function = library.renameat2
            flag = 0x00000001  # RENAME_NOREPLACE
        else:
            return None, None
        function.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        function.restype = ctypes.c_int
        return function, flag
    except (AttributeError, OSError, TypeError):
        return None, None


_NATIVE_RENAME_NOREPLACE, _NATIVE_RENAME_NOREPLACE_FLAG = (
    _load_native_rename_noreplace()
)
_PINNED_NATIVE_RENAME_NOREPLACE = _NATIVE_RENAME_NOREPLACE
_PINNED_NATIVE_RENAME_NOREPLACE_FLAG = _NATIVE_RENAME_NOREPLACE_FLAG
_PINNED_NATIVE_RENAME_ARGTYPES = (
    None
    if _NATIVE_RENAME_NOREPLACE is None
    else tuple(_NATIVE_RENAME_NOREPLACE.argtypes)
)
_PINNED_NATIVE_RENAME_RESTYPE = (
    None
    if _NATIVE_RENAME_NOREPLACE is None
    else _NATIVE_RENAME_NOREPLACE.restype
)
_PINNED_CTYPES_GET_ERRNO = ctypes.get_errno
_PINNED_CTYPES_SET_ERRNO = ctypes.set_errno


class PhysicalProductionInputArchiveError(ValueError):
    """The physical C2 archive is not exact, private, or authenticated."""


class PhysicalProductionInputCapacityError(PhysicalProductionInputArchiveError):
    """A fixed traversal, row, or disk bound was exceeded."""


@dataclasses.dataclass(frozen=True, slots=True)
class PhysicalC2FileDescriptor:
    kind: str
    relative_path: str
    byte_count: int
    sha256: str
    row_count: int
    maximum_record_byte_count: int

    def __post_init__(self) -> None:
        if type(self.kind) is not str or not self.kind:
            raise PhysicalProductionInputArchiveError("file kind must be exact text")
        if (
            type(self.relative_path) is not str
            or not self.relative_path
            or Path(self.relative_path).name != self.relative_path
        ):
            raise PhysicalProductionInputArchiveError(
                "archive file path must be one canonical basename"
            )
        try:
            require_int(self.byte_count, "file byte_count", minimum=1)
            require_int(self.row_count, "file row_count", minimum=0)
            require_int(
                self.maximum_record_byte_count,
                "file maximum_record_byte_count",
                minimum=0,
            )
            require_sha256(self.sha256, "file sha256")
        except ValueError as exc:
            raise PhysicalProductionInputArchiveError(
                "archive file descriptor is malformed"
            ) from exc
        if self.byte_count > MAX_ARCHIVE_FILE_BYTES:
            raise PhysicalProductionInputCapacityError(
                "archive file exceeds the fixed byte bound"
            )
        if self.maximum_record_byte_count > MAX_RECORD_BYTES:
            raise PhysicalProductionInputCapacityError(
                "archive record exceeds the fixed byte bound"
            )

    def to_record(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "relative_path": self.relative_path,
            "byte_count": self.byte_count,
            "sha256": self.sha256,
            "row_count": self.row_count,
            "maximum_record_byte_count": self.maximum_record_byte_count,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class PhysicalProductionInputBatchArchive:
    signal_arm: SignalArm
    batch_id: str
    batch_sha256: str
    source_view: InputView
    source_view_label: str
    total_source_row_count: int
    source_view_included_count: int
    directional_candidate_count: int
    normalized_row_count: int
    refused_directional_count: int
    admissions: PhysicalC2FileDescriptor
    normalized_rows: PhysicalC2FileDescriptor

    @property
    def all_directional_rows_admitted(self) -> bool:
        return (
            self.directional_candidate_count > 0
            and self.refused_directional_count == 0
        )

    def to_record(self) -> dict[str, object]:
        return {
            "signal_arm": self.signal_arm.value,
            "batch_id": self.batch_id,
            "batch_sha256": self.batch_sha256,
            "source_view": self.source_view.value,
            "source_view_label": self.source_view_label,
            "total_source_row_count": self.total_source_row_count,
            "source_view_included_count": self.source_view_included_count,
            "directional_candidate_count": self.directional_candidate_count,
            "normalized_row_count": self.normalized_row_count,
            "refused_directional_count": self.refused_directional_count,
            "admissions": self.admissions.to_record(),
            "normalized_rows": self.normalized_rows.to_record(),
        }


@dataclasses.dataclass(frozen=True, slots=True, weakref_slot=True, init=False)
class PhysicalProductionInputArchive:
    schema: str
    archive_id: str
    archive_sha256: str
    archive_path: Path
    accepted_risk_archive: object | None
    parent_archive_id: str
    parent_archive_sha256: str
    fixture_only: bool
    pair_id: str
    pair_sha256: str
    evidence_authority_id: str
    evidence_authority_sha256: str
    source_bindings: tuple[EvidenceSourceBinding, ...]
    source_projection_sha256: str
    row_projection_sha256: str
    evidence_row_count: int
    component_present_counts: tuple[tuple[str, int], ...]
    evidence_rows: PhysicalC2FileDescriptor
    evidence_package: PhysicalC2FileDescriptor
    comparison_report: PhysicalC2FileDescriptor
    comparison_report_sha256: str
    batches: tuple[PhysicalProductionInputBatchArchive, ...]
    maximum_source_row_count: int
    maximum_evidence_row_count: int
    full_pair_materialized: bool
    full_evidence_materialized: bool
    full_admission_census_materialized: bool
    provider_access: bool
    credential_access: bool
    quantconnect_access: bool
    outcome_access: bool
    result_access: bool
    deployment: bool
    orders: bool
    trading: bool


@dataclasses.dataclass(frozen=True, slots=True)
class PhysicalNormalizedEvidenceRow:
    """One C2 normalized row joined to its exact physical evidence row."""

    normalized_row: NormalizedPreOutcomeRow
    evidence: ProductionRowEvidence


@dataclasses.dataclass(frozen=True, slots=True)
class _RawJson:
    chunks: Callable[[], Iterator[bytes]]


@dataclasses.dataclass(frozen=True, slots=True)
class _JsonArray:
    items: Callable[[], Iterator[bytes]]


_AUTHORITIES: dict[
    int,
    tuple[
        weakref.ReferenceType[PhysicalProductionInputArchive],
        tuple[object, ...],
        tuple[object, ...],
        int,
        tuple[int, int],
    ],
] = {}
_AUTHORITY_LOCK = threading.RLock()


def _forget(identity: int, reference: object) -> None:
    with _AUTHORITY_LOCK:
        current = _AUTHORITIES.get(identity)
        if current is not None and current[0] is reference:
            _AUTHORITIES.pop(identity, None)


def _canonical_fragment(value: object) -> bytes:
    return canonical_json_bytes(value)[:-1]


def _iter_json_value(value: object) -> Iterator[bytes]:
    if type(value) is _RawJson:
        yield from value.chunks()
        return
    if type(value) is _JsonArray:
        yield b"["
        first = True
        for item in value.items():
            if type(item) is not bytes:
                raise PhysicalProductionInputArchiveError(
                    "canonical array yielded a non-bytes member"
                )
            if not first:
                yield b","
            yield item
            first = False
        yield b"]"
        return
    yield _canonical_fragment(value)


def _iter_canonical_object(
    values: Mapping[str, object], *, terminate: bool
) -> Iterator[bytes]:
    if type(values) is not dict or any(type(key) is not str for key in values):
        raise PhysicalProductionInputArchiveError(
            "streamed canonical object requires an exact string-keyed dict"
        )
    yield b"{"
    for index, key in enumerate(sorted(values)):
        if index:
            yield b","
        yield _canonical_fragment(key)
        yield b":"
        yield from _iter_json_value(values[key])
    yield b"}"
    if terminate:
        yield b"\n"


def _digest_chunks(chunks: Iterable[bytes]) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    for chunk in chunks:
        if type(chunk) is not bytes:
            raise PhysicalProductionInputArchiveError(
                "digest stream yielded non-bytes"
            )
        digest.update(chunk)
        count += len(chunk)
        if count > MAX_ARCHIVE_FILE_BYTES:
            raise PhysicalProductionInputCapacityError(
                "canonical stream exceeds its fixed byte bound"
            )
    return count, digest.hexdigest()


def _archive_fingerprint(value: PhysicalProductionInputArchive) -> tuple[object, ...]:
    return tuple(
        id(item) if field.name == "accepted_risk_archive" else item
        for field, item in (
            (field, getattr(value, field.name)) for field in dataclasses.fields(value)
        )
    )


def _archive_topology(value: PhysicalProductionInputArchive) -> tuple[object, ...]:
    return (
        id(value.accepted_risk_archive),
        id(value.source_bindings),
        tuple(id(item) for item in value.source_bindings),
        id(value.component_present_counts),
        tuple(id(item) for item in value.component_present_counts),
        id(value.evidence_rows),
        id(value.evidence_package),
        id(value.comparison_report),
        id(value.batches),
        tuple(
            (
                id(batch),
                id(batch.admissions),
                id(batch.normalized_rows),
            )
            for batch in value.batches
        ),
    )


def _require_dirfd_support() -> None:
    required = (os.open, os.mkdir, os.rename, os.stat, os.unlink, os.rmdir)
    if (
        os.name == "nt"
        or not hasattr(os, "O_DIRECTORY")
        or not hasattr(os, "O_NOFOLLOW")
        or any(call not in os.supports_dir_fd for call in required)
    ):
        raise PhysicalProductionInputArchiveError(
            "physical C2 requires POSIX dirfd and no-follow support"
        )


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )


def _require_private_directory_metadata(
    metadata: os.stat_result, name: str
) -> None:
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        raise PhysicalProductionInputArchiveError(
            f"{name} must be an owner-held 0700 directory"
        )


def _open_directory_path(path: Path, *, name: str) -> tuple[Path, int]:
    """Open an absolute directory component-by-component without links."""

    _require_dirfd_support()
    if not isinstance(path, Path):
        raise PhysicalProductionInputArchiveError(f"{name} must be a Path")
    absolute = Path(os.path.abspath(path))
    parts = absolute.parts
    if not absolute.is_absolute() or not parts:
        raise PhysicalProductionInputArchiveError(f"{name} must be absolute")
    try:
        descriptor = os.open(absolute.anchor, _directory_open_flags())
    except OSError as exc:
        raise PhysicalProductionInputArchiveError(
            f"{name} root directory is unavailable"
        ) from exc
    try:
        for component in parts[1:]:
            try:
                child = os.open(
                    component,
                    _directory_open_flags(),
                    dir_fd=descriptor,
                )
            except OSError as exc:
                raise PhysicalProductionInputArchiveError(
                    f"{name} must not traverse a link and must be a directory"
                ) from exc
            os.close(descriptor)
            descriptor = child
        _require_private_directory_metadata(os.fstat(descriptor), name)
        return absolute, descriptor
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def _safe_basename(value: str, name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
    ):
        raise PhysicalProductionInputArchiveError(f"{name} name is unsafe")
    return value


def _open_private_child_directory(
    parent_fd: int, child: str, name: str
) -> int:
    _safe_basename(child, name)
    descriptor: int | None = None
    try:
        descriptor = os.open(child, _directory_open_flags(), dir_fd=parent_fd)
        _require_private_directory_metadata(os.fstat(descriptor), name)
        return descriptor
    except PhysicalProductionInputArchiveError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise PhysicalProductionInputArchiveError(
            f"{name} is unavailable or link-like"
        ) from exc


def _directory_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _require_pinned_child_identity(
    parent_fd: int, child: str, child_fd: int, name: str
) -> None:
    try:
        opened = os.fstat(child_fd)
        named = os.stat(child, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise PhysicalProductionInputArchiveError(
            f"{name} directory identity is unavailable"
        ) from exc
    _require_private_directory_metadata(opened, name)
    _require_private_directory_metadata(named, name)
    if _directory_identity(opened) != _directory_identity(named):
        raise PhysicalProductionInputArchiveError(
            f"{name} directory identity changed"
        )


def _require_reopened_directory_identity(
    path: Path, descriptor: int, name: str
) -> None:
    reopened_fd: int | None = None
    try:
        _reopened_path, reopened_fd = _open_directory_path(path, name=name)
        if _directory_identity(os.fstat(reopened_fd)) != _directory_identity(
            os.fstat(descriptor)
        ):
            raise PhysicalProductionInputArchiveError(
                f"{name} path identity changed"
            )
    finally:
        if reopened_fd is not None:
            os.close(reopened_fd)


def _require_live_directory_path_identity(
    path: Path, descriptor: int, name: str
) -> None:
    try:
        named = os.stat(path, follow_symlinks=False)
        opened = os.fstat(descriptor)
    except OSError as exc:
        raise PhysicalProductionInputArchiveError(
            f"{name} path identity is unavailable"
        ) from exc
    _require_private_directory_metadata(named, name)
    _require_private_directory_metadata(opened, name)
    if _directory_identity(named) != _directory_identity(opened):
        raise PhysicalProductionInputArchiveError(
            f"{name} path identity changed"
        )


def _entry_exists_at(parent_fd: int, name: str) -> bool:
    _safe_basename(name, "archive entry")
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise PhysicalProductionInputArchiveError(
            "archive directory entry could not be inspected"
        ) from exc
    return True


def _fsync_fd(descriptor: int, name: str) -> None:
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise PhysicalProductionInputArchiveError(
            f"{name} directory sync failed"
        ) from exc


def _rename_at(parent_fd: int, source: str, destination: str) -> None:
    """Atomically rename without ever replacing an existing destination."""

    _safe_basename(source, "atomic rename source")
    _safe_basename(destination, "atomic rename destination")
    if (
        _NATIVE_RENAME_NOREPLACE is not _PINNED_NATIVE_RENAME_NOREPLACE
        or _NATIVE_RENAME_NOREPLACE_FLAG
        is not _PINNED_NATIVE_RENAME_NOREPLACE_FLAG
        or ctypes.get_errno is not _PINNED_CTYPES_GET_ERRNO
        or ctypes.set_errno is not _PINNED_CTYPES_SET_ERRNO
        or _PINNED_NATIVE_RENAME_NOREPLACE is None
        or type(_PINNED_NATIVE_RENAME_NOREPLACE_FLAG) is not int
    ):
        raise PhysicalProductionInputArchiveError(
            "atomic no-replace rename authority is unavailable"
        )
    _PINNED_CTYPES_SET_ERRNO(0)
    result = _PINNED_NATIVE_RENAME_NOREPLACE(
        parent_fd,
        os.fsencode(source),
        parent_fd,
        os.fsencode(destination),
        _PINNED_NATIVE_RENAME_NOREPLACE_FLAG,
    )
    if result == 0:
        return
    error_number = _PINNED_CTYPES_GET_ERRNO()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise PhysicalProductionInputArchiveError(
            "atomic no-replace rename destination exists"
        )
    raise PhysicalProductionInputArchiveError(
        "atomic no-replace rename failed"
    )


def _create_private_stage_at(root_fd: int) -> tuple[str, int]:
    for _attempt in range(32):
        stage_name = f".arv2-c2-{os.getpid()}-{secrets.token_hex(12)}"
        try:
            os.mkdir(stage_name, 0o700, dir_fd=root_fd)
        except FileExistsError:
            continue
        except OSError as exc:
            raise PhysicalProductionInputArchiveError(
                "physical C2 staging directory could not be created"
            ) from exc
        try:
            stage_fd = _open_private_child_directory(
                root_fd, stage_name, "physical C2 staging directory"
            )
            _require_pinned_child_identity(
                root_fd,
                stage_name,
                stage_fd,
                "physical C2 staging directory",
            )
            return stage_name, stage_fd
        except BaseException:
            # The hidden directory is preserved if it cannot be pinned safely.
            raise
    raise PhysicalProductionInputArchiveError(
        "physical C2 staging name budget was exhausted"
    )


def _rollback_published_archive(
    *,
    root_path: Path,
    root_fd: int,
    final_name: str,
    stage_name: str,
    stage_fd: int,
) -> None:
    try:
        _require_pinned_child_identity(
            root_fd, final_name, stage_fd, "published physical C2 archive"
        )
        if _entry_exists_at(root_fd, stage_name):
            raise PhysicalProductionInputArchiveError(
                "physical C2 rollback staging name is occupied"
            )
        _rename_at(root_fd, final_name, stage_name)
        _require_pinned_child_identity(
            root_fd,
            stage_name,
            stage_fd,
            "rolled-back physical C2 staging directory",
        )
    except (OSError, PhysicalProductionInputArchiveError) as exc:
        raise PhysicalProductionInputArchiveError(
            "physical C2 publication state is ambiguous after rollback failure"
        ) from exc
    try:
        _fsync_fd(root_fd, "physical C2 root rollback")
        _require_reopened_directory_identity(
            root_path, root_fd, "physical C2 archive root"
        )
    except PhysicalProductionInputArchiveError as exc:
        raise PhysicalProductionInputArchiveError(
            "physical C2 publication state is ambiguous after rollback sync failure"
        ) from exc


def _quarantine_created_file_at(
    parent_fd: int,
    filename: str,
    expected: tuple[int, int],
    name: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, int]:
    """Atomically detach one expected leaf before any destructive unlink.

    ``unlinkat`` cannot assert an expected inode.  Moving the leaf to an
    unpredictable quarantine name beneath the already-held directory lets us
    verify what the rename actually detached.  A mismatch is never unlinked;
    the caller must preserve the staging directory for inspection.
    """

    _safe_basename(filename, name)
    held_fd: int | None = None
    quarantine_name: str | None = None
    try:
        held_fd = os.open(
            filename,
            os.O_RDONLY
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_fd,
        )
        held = os.fstat(held_fd)
        _require_private_regular_metadata(
            held, name, allow_empty=allow_empty
        )
        if _regular_inode_identity(held) != expected:
            raise PhysicalProductionInputArchiveError(
                f"{name} quarantine is ambiguous"
            )
        for _attempt in range(32):
            candidate = f".arv2-delete-{secrets.token_hex(16)}"
            if not _entry_exists_at(parent_fd, candidate):
                quarantine_name = candidate
                break
        if quarantine_name is None:
            raise PhysicalProductionInputArchiveError(
                f"{name} quarantine name budget was exhausted"
            )
        _rename_at(parent_fd, filename, quarantine_name)
        quarantined = _require_created_file_identity_at(
            parent_fd,
            quarantine_name,
            expected,
            name,
            allow_empty=allow_empty,
        )
        held_after = os.fstat(held_fd)
        if (
            _regular_inode_identity(held_after) != expected
            or _regular_file_identity(held_after)
            != _regular_file_identity(quarantined)
        ):
            raise PhysicalProductionInputArchiveError(
                f"{name} quarantine is ambiguous"
            )
        return quarantine_name, held_fd
    except BaseException as exc:
        if held_fd is not None:
            try:
                os.close(held_fd)
            except OSError:
                pass
        if (
            isinstance(exc, PhysicalProductionInputArchiveError)
            and str(exc) == f"{name} quarantine name budget was exhausted"
        ):
            raise
        raise PhysicalProductionInputArchiveError(
            f"{name} quarantine is ambiguous"
        ) from exc


def _unlink_quarantined_file_at(
    parent_fd: int,
    quarantine_name: str,
    held_fd: int,
    expected: tuple[int, int],
    name: str,
    *,
    allow_empty: bool = False,
) -> None:
    """Unlink only a still-named quarantine leaf bound to its held inode."""

    try:
        held = os.fstat(held_fd)
        named = _require_created_file_identity_at(
            parent_fd,
            quarantine_name,
            expected,
            name,
            allow_empty=allow_empty,
        )
        if (
            _regular_inode_identity(held) != expected
            or _regular_file_identity(held) != _regular_file_identity(named)
        ):
            raise PhysicalProductionInputArchiveError(
                f"{name} quarantine is ambiguous"
            )
        os.unlink(quarantine_name, dir_fd=parent_fd)
    except BaseException as exc:
        if isinstance(exc, PhysicalProductionInputArchiveError):
            raise
        raise PhysicalProductionInputArchiveError(
            f"{name} quarantine is ambiguous"
        ) from exc


def _safe_cleanup_stage_at(
    *,
    root_path: Path,
    root_fd: int,
    stage_name: str,
    stage_fd: int,
    created_files: Mapping[str, tuple[int, int]],
) -> bool:
    """Remove only the still-pinned private staging tree we created."""

    try:
        _require_reopened_directory_identity(
            root_path, root_fd, "physical C2 archive root"
        )
        _require_pinned_child_identity(
            root_fd,
            stage_name,
            stage_fd,
            "physical C2 staging directory",
        )
        names = set(os.listdir(stage_fd))
        if names != set(created_files):
            return False
        for filename, identity in created_files.items():
            _require_created_file_identity_at(
                stage_fd,
                filename,
                identity,
                "physical C2 staging member",
                allow_empty=True,
            )
    except (OSError, PhysicalProductionInputArchiveError):
        return False
    quarantined: list[tuple[str, int, tuple[int, int]]] = []
    try:
        for filename in sorted(created_files):
            quarantine_name, held_fd = _quarantine_created_file_at(
                stage_fd,
                filename,
                created_files[filename],
                "physical C2 staging member",
                allow_empty=True,
            )
            quarantined.append(
                (quarantine_name, held_fd, created_files[filename])
            )
        if set(os.listdir(stage_fd)) != {
            quarantine_name
            for quarantine_name, _held_fd, _identity in quarantined
        }:
            return False
        for quarantine_name, held_fd, identity in quarantined:
            _require_created_file_identity_at(
                stage_fd,
                quarantine_name,
                identity,
                "physical C2 staging member",
                allow_empty=True,
            )
            if _regular_inode_identity(os.fstat(held_fd)) != identity:
                return False
        for quarantine_name, held_fd, identity in quarantined:
            _unlink_quarantined_file_at(
                stage_fd,
                quarantine_name,
                held_fd,
                identity,
                "physical C2 staging member",
                allow_empty=True,
            )
        _fsync_fd(stage_fd, "physical C2 staging cleanup")
        if os.listdir(stage_fd):
            return False
        _require_pinned_child_identity(
            root_fd,
            stage_name,
            stage_fd,
            "physical C2 staging directory",
        )
        os.rmdir(stage_name, dir_fd=root_fd)
        _fsync_fd(root_fd, "physical C2 root cleanup")
        _require_reopened_directory_identity(
            root_path, root_fd, "physical C2 archive root"
        )
        return True
    except (OSError, PhysicalProductionInputArchiveError):
        return False
    finally:
        for _quarantine_name, held_fd, _identity in quarantined:
            try:
                os.close(held_fd)
            except OSError:
                pass


def _require_build_directories_live(
    *,
    root_path: Path,
    root_fd: int,
    stage_name: str,
    stage_fd: int,
) -> None:
    _require_reopened_directory_identity(
        root_path, root_fd, "physical C2 archive root"
    )
    _require_pinned_child_identity(
        root_fd,
        stage_name,
        stage_fd,
        "physical C2 staging directory",
    )


def _regular_inode_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _regular_file_identity(
    metadata: os.stat_result,
) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _require_private_regular_metadata(
    metadata: os.stat_result,
    name: str,
    *,
    allow_empty: bool = False,
) -> None:
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or (not allow_empty and metadata.st_size < 1)
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        raise PhysicalProductionInputArchiveError(
            f"{name} is not an owner-held 0600 single-link regular file"
        )


def _require_created_file_identity_at(
    parent_fd: int,
    filename: str,
    expected: tuple[int, int],
    name: str,
    *,
    allow_empty: bool = False,
) -> os.stat_result:
    try:
        current = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise PhysicalProductionInputArchiveError(
            f"{name} identity is unavailable"
        ) from exc
    _require_private_regular_metadata(current, name, allow_empty=allow_empty)
    if _regular_inode_identity(current) != expected:
        raise PhysicalProductionInputArchiveError(f"{name} identity changed")
    return current


def _require_visited_file_identity_at(
    parent_fd: int,
    filename: str,
    expected: tuple[int, int, int, int, int],
    name: str,
) -> None:
    try:
        current = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise PhysicalProductionInputArchiveError(
            f"{name} identity changed after traversal"
        ) from exc
    _require_private_regular_metadata(current, name)
    if _regular_file_identity(current) != expected:
        raise PhysicalProductionInputArchiveError(
            f"{name} identity changed after traversal"
        )


def _pin_private_regular_identity_at(
    parent_fd: int,
    filename: str,
    *,
    expected_bytes: int,
    name: str,
) -> tuple[int, int, int, int, int]:
    _safe_basename(filename, name)
    try:
        metadata = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise PhysicalProductionInputArchiveError(
            f"{name} identity is unavailable"
        ) from exc
    _require_private_regular_metadata(metadata, name)
    if (
        metadata.st_size != expected_bytes
        or expected_bytes < 1
        or expected_bytes > MAX_ARCHIVE_FILE_BYTES
    ):
        raise PhysicalProductionInputArchiveError(
            f"{name} is not the expected private regular file"
        )
    return _regular_file_identity(metadata)


def _read_private_file_at(
    parent_fd: int,
    filename: str,
    *,
    maximum_bytes: int,
    expected_bytes: int | None = None,
    expected_sha256: str | None = None,
    name: str,
) -> tuple[bytes, tuple[int, int, int, int, int]]:
    _safe_basename(filename, name)
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        named_before = os.stat(
            filename, dir_fd=parent_fd, follow_symlinks=False
        )
        descriptor = os.open(filename, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise PhysicalProductionInputArchiveError(
            f"{name} could not be opened without following links"
        ) from exc
    try:
        before = os.fstat(descriptor)
        _require_private_regular_metadata(named_before, name)
        _require_private_regular_metadata(before, name)
        if (
            _regular_file_identity(named_before)
            != _regular_file_identity(before)
            or before.st_size > maximum_bytes
        ):
            raise PhysicalProductionInputArchiveError(
                f"{name} is not the pinned bounded archive member"
            )
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(IO_CHUNK_BYTES, remaining))
            if not chunk:
                raise PhysicalProductionInputArchiveError(
                    f"{name} was truncated while read"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise PhysicalProductionInputArchiveError(
                f"{name} grew while read"
            )
        after = os.fstat(descriptor)
        named_after = os.stat(
            filename, dir_fd=parent_fd, follow_symlinks=False
        )
    except PhysicalProductionInputArchiveError:
        raise
    except OSError as exc:
        raise PhysicalProductionInputArchiveError(
            f"{name} changed while being read"
        ) from exc
    finally:
        os.close(descriptor)
    identity = _regular_file_identity(before)
    if (
        _regular_file_identity(after) != identity
        or _regular_file_identity(named_after) != identity
    ):
        raise PhysicalProductionInputArchiveError(
            f"{name} changed while being read"
        )
    payload = b"".join(chunks)
    if expected_bytes is not None and len(payload) != expected_bytes:
        raise PhysicalProductionInputArchiveError(
            f"{name} byte count changed"
        )
    if expected_sha256 is not None and sha256_bytes(payload) != expected_sha256:
        raise PhysicalProductionInputArchiveError(f"{name} hash changed")
    return payload, identity


def _iter_private_file_at(
    parent_fd: int,
    filename: str,
    *,
    expected_bytes: int,
    expected_sha256: str,
    name: str,
    pinned_identity: tuple[int, int, int, int, int] | None = None,
    identity_sink: dict[str, tuple[int, int, int, int, int]] | None = None,
    live_directory: tuple[Path, int, str] | None = None,
) -> Iterator[bytes]:
    identity = pinned_identity or _pin_private_regular_identity_at(
        parent_fd,
        filename,
        expected_bytes=expected_bytes,
        name=name,
    )
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(filename, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise PhysicalProductionInputArchiveError(
            f"{name} could not be opened without following links"
        ) from exc
    digest = hashlib.sha256()
    observed = 0
    try:
        before = os.fstat(descriptor)
        _require_private_regular_metadata(before, name)
        if _regular_file_identity(before) != identity:
            raise PhysicalProductionInputArchiveError(
                f"{name} identity changed before traversal"
            )
        while True:
            chunk = os.read(descriptor, IO_CHUNK_BYTES)
            if not chunk:
                break
            observed += len(chunk)
            digest.update(chunk)
            _require_visited_file_identity_at(
                parent_fd, filename, identity, name
            )
            if live_directory is not None:
                _require_live_directory_path_identity(*live_directory)
            yield chunk
            _require_visited_file_identity_at(
                parent_fd, filename, identity, name
            )
            if live_directory is not None:
                _require_live_directory_path_identity(*live_directory)
        after = os.fstat(descriptor)
    except PhysicalProductionInputArchiveError:
        raise
    except OSError as exc:
        raise PhysicalProductionInputArchiveError(
            f"{name} changed during bounded traversal"
        ) from exc
    finally:
        os.close(descriptor)
    if (
        observed != expected_bytes
        or digest.hexdigest() != expected_sha256
        or _regular_file_identity(after) != identity
    ):
        raise PhysicalProductionInputArchiveError(
            f"{name} changed during bounded traversal"
        )
    _require_visited_file_identity_at(parent_fd, filename, identity, name)
    if live_directory is not None:
        _require_live_directory_path_identity(*live_directory)
    if identity_sink is not None:
        identity_sink[filename] = identity


def _iter_file_fragment_at(
    parent_fd: int,
    filename: str,
    *,
    expected_bytes: int,
    expected_sha256: str,
    live_directory: tuple[Path, int, str] | None = None,
) -> Iterator[bytes]:
    pending = b""
    for chunk in _iter_private_file_at(
        parent_fd,
        filename,
        expected_bytes=expected_bytes,
        expected_sha256=expected_sha256,
        name=filename,
        live_directory=live_directory,
    ):
        if pending:
            chunk = pending + chunk
            pending = b""
        if len(chunk) == 1:
            pending = chunk
            continue
        yield chunk[:-1]
        pending = chunk[-1:]
    if pending != b"\n":
        raise PhysicalProductionInputArchiveError(
            "canonical archive member lacks exactly one LF terminator"
        )


def _iter_jsonl_fragments_at(
    parent_fd: int,
    filename: str,
    descriptor: PhysicalC2FileDescriptor,
    *,
    identity_sink: dict[str, tuple[int, int, int, int, int]] | None = None,
    live_directory: tuple[Path, int, str] | None = None,
) -> Iterator[bytes]:
    identity = _pin_private_regular_identity_at(
        parent_fd,
        filename,
        expected_bytes=descriptor.byte_count,
        name=filename,
    )
    if descriptor.row_count == 0:
        if live_directory is not None:
            _require_live_directory_path_identity(*live_directory)
        payload, observed_identity = _read_private_file_at(
            parent_fd,
            filename,
            maximum_bytes=1,
            expected_bytes=descriptor.byte_count,
            expected_sha256=descriptor.sha256,
            name=filename,
        )
        if payload != b"\n" or observed_identity != identity:
            raise PhysicalProductionInputArchiveError(
                "empty archive JSONL sentinel changed"
            )
        if live_directory is not None:
            _require_live_directory_path_identity(*live_directory)
        if identity_sink is not None:
            identity_sink[filename] = identity
        return
    pending = bytearray()
    observed_rows = 0
    for chunk in _iter_private_file_at(
        parent_fd,
        filename,
        expected_bytes=descriptor.byte_count,
        expected_sha256=descriptor.sha256,
        name=filename,
        pinned_identity=identity,
        identity_sink=identity_sink,
        live_directory=live_directory,
    ):
        pending.extend(chunk)
        while True:
            newline = pending.find(b"\n")
            if newline < 0:
                break
            line = bytes(pending[:newline])
            del pending[: newline + 1]
            if not line or len(line) + 1 > descriptor.maximum_record_byte_count:
                raise PhysicalProductionInputCapacityError(
                    "archive JSONL row is empty or exceeds its recorded bound"
                )
            observed_rows += 1
            if observed_rows > descriptor.row_count:
                raise PhysicalProductionInputArchiveError(
                    "archive JSONL contains surplus rows"
                )
            _require_visited_file_identity_at(
                parent_fd, filename, identity, filename
            )
            if live_directory is not None:
                _require_live_directory_path_identity(*live_directory)
            yield line
            _require_visited_file_identity_at(
                parent_fd, filename, identity, filename
            )
            if live_directory is not None:
                _require_live_directory_path_identity(*live_directory)
        if len(pending) + 1 > descriptor.maximum_record_byte_count:
            raise PhysicalProductionInputCapacityError(
                "archive JSONL row exceeds its recorded bound"
            )
    if pending or observed_rows != descriptor.row_count:
        raise PhysicalProductionInputArchiveError(
            "archive JSONL lost termination or row-count identity"
        )


class _PrivateJsonlWriter:
    def __init__(
        self,
        parent_fd: int,
        filename: str,
        kind: str,
        created_files: dict[str, tuple[int, int]],
    ) -> None:
        self._parent_fd = parent_fd
        self.filename = _safe_basename(filename, kind)
        self.kind = kind
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0)
        )
        self._descriptor = os.open(
            self.filename, flags, 0o600, dir_fd=self._parent_fd
        )
        os.fchmod(self._descriptor, 0o600)
        created = os.fstat(self._descriptor)
        _require_private_regular_metadata(created, kind, allow_empty=True)
        self._inode_identity = _regular_inode_identity(created)
        created_files[self.filename] = self._inode_identity
        self._digest = hashlib.sha256()
        self._byte_count = 0
        self._row_count = 0
        self._maximum_record_byte_count = 0
        self._closed = False

    def write_record(self, value: object) -> None:
        if self._closed:
            raise PhysicalProductionInputArchiveError("archive writer is closed")
        payload = canonical_json_bytes(value)
        if not payload.endswith(b"\n") or len(payload) > MAX_RECORD_BYTES:
            raise PhysicalProductionInputCapacityError(
                "canonical archive row exceeds its fixed bound"
            )
        if self._byte_count + len(payload) > MAX_ARCHIVE_FILE_BYTES:
            raise PhysicalProductionInputCapacityError(
                "archive JSONL file exceeds its fixed byte bound"
            )
        self._write(payload)
        self._row_count += 1
        self._maximum_record_byte_count = max(
            self._maximum_record_byte_count, len(payload)
        )

    def _write(self, payload: bytes) -> None:
        self._digest.update(payload)
        self._byte_count += len(payload)
        view = memoryview(payload)
        while view:
            written = os.write(self._descriptor, view)
            if written <= 0:
                raise PhysicalProductionInputArchiveError("archive writer stalled")
            view = view[written:]

    def finish(self) -> PhysicalC2FileDescriptor:
        if self._closed:
            raise PhysicalProductionInputArchiveError("archive writer closed twice")
        if self._byte_count == 0:
            # JSONL with zero rows is still represented by a single LF-free JSON
            # sentinel file so that every authenticated member is nonempty.
            self._write(b"\n")
            self._maximum_record_byte_count = 1
        os.fsync(self._descriptor)
        metadata = os.fstat(self._descriptor)
        _require_private_regular_metadata(metadata, self.kind)
        if (
            _regular_inode_identity(metadata) != self._inode_identity
            or metadata.st_size != self._byte_count
        ):
            raise PhysicalProductionInputArchiveError(
                "archive writer identity changed before close"
            )
        _require_created_file_identity_at(
            self._parent_fd,
            self.filename,
            self._inode_identity,
            self.kind,
        )
        os.close(self._descriptor)
        self._closed = True
        return PhysicalC2FileDescriptor(
            kind=self.kind,
            relative_path=self.filename,
            byte_count=self._byte_count,
            sha256=self._digest.hexdigest(),
            row_count=self._row_count,
            maximum_record_byte_count=self._maximum_record_byte_count,
        )

    def abort(self) -> None:
        if not self._closed:
            try:
                os.close(self._descriptor)
            finally:
                self._closed = True


def _write_private_chunks_at(
    parent_fd: int,
    filename: str,
    chunks: Iterable[bytes],
    *,
    created_files: dict[str, tuple[int, int]],
) -> tuple[int, str]:
    filename = _safe_basename(filename, "archive file")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = os.open(filename, flags, 0o600, dir_fd=parent_fd)
    digest = hashlib.sha256()
    count = 0
    try:
        os.fchmod(descriptor, 0o600)
        created = os.fstat(descriptor)
        _require_private_regular_metadata(
            created, "archive file", allow_empty=True
        )
        inode_identity = _regular_inode_identity(created)
        created_files[filename] = inode_identity
        for chunk in chunks:
            if type(chunk) is not bytes:
                raise PhysicalProductionInputArchiveError(
                    "archive writer received a non-bytes chunk"
                )
            count += len(chunk)
            if count > MAX_ARCHIVE_FILE_BYTES:
                raise PhysicalProductionInputCapacityError(
                    "archive file exceeds its fixed byte bound"
                )
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise PhysicalProductionInputArchiveError(
                        "archive writer stalled"
                    )
                view = view[written:]
        if count < 1:
            raise PhysicalProductionInputArchiveError(
                "archive writer cannot publish an empty canonical document"
            )
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        _require_private_regular_metadata(metadata, "archive file")
        if (
            _regular_inode_identity(metadata) != inode_identity
            or metadata.st_size != count
        ):
            raise PhysicalProductionInputArchiveError(
                "archive file identity changed before close"
            )
        _require_created_file_identity_at(
            parent_fd,
            filename,
            inode_identity,
            "archive file",
        )
    finally:
        os.close(descriptor)
    return count, digest.hexdigest()


def _descriptor_for_document(
    *,
    kind: str,
    path: Path,
    byte_count: int,
    sha256: str,
) -> PhysicalC2FileDescriptor:
    return PhysicalC2FileDescriptor(
        kind=kind,
        relative_path=path.name,
        byte_count=byte_count,
        sha256=sha256,
        row_count=1,
        maximum_record_byte_count=min(byte_count, MAX_RECORD_BYTES),
    )


def _strict_record(payload: bytes, name: str) -> dict[str, Any]:
    if type(payload) is not bytes or not payload:
        raise PhysicalProductionInputArchiveError(f"{name} is empty")
    try:
        value = strict_json_loads(decode_utf8(payload, name), name)
    except (CanonicalEvidenceError, RecursionError) as exc:
        raise PhysicalProductionInputArchiveError(
            f"{name} is not strict JSON"
        ) from exc
    if type(value) is not dict or canonical_json_bytes(value)[:-1] != payload:
        raise PhysicalProductionInputArchiveError(
            f"{name} is not one canonical JSON object"
        )
    return value


def _exact_fields(
    value: object,
    expected: frozenset[str],
    name: str,
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise PhysicalProductionInputArchiveError(f"{name} fields changed")
    return value


_LOCATOR_FIELDS = frozenset(field.name for field in dataclasses.fields(CaptureRowLocator))
_EVIDENCE_FIELDS = frozenset(field.name for field in dataclasses.fields(ProductionRowEvidence))
_NORMALIZED_FIELDS = frozenset(
    field.name for field in dataclasses.fields(NormalizedPreOutcomeRow)
)


def _decode_locator(value: object) -> CaptureRowLocator:
    raw = _exact_fields(value, _LOCATOR_FIELDS, "C2 row locator")
    try:
        return CaptureRowLocator(
            capture_id=raw["capture_id"],
            source_role=MassiveSourceRole(raw["source_role"]),
            page_number=raw["page_number"],
            provider_rows_sha256=raw["provider_rows_sha256"],
            row_offset=raw["row_offset"],
            raw_row_sha256=raw["raw_row_sha256"],
        )
    except (TypeError, ValueError) as exc:
        raise PhysicalProductionInputArchiveError(
            "C2 row locator is invalid"
        ) from exc


def _fraction(value: object, name: str) -> Fraction:
    if (
        type(value) is not list
        or len(value) != 2
        or type(value[0]) is not int
        or type(value[1]) is not int
        or value[1] == 0
    ):
        raise PhysicalProductionInputArchiveError(
            f"{name} is not an exact fraction"
        )
    return Fraction(value[0], value[1])


def _construct_component(name: str, value: object) -> object | None:
    if value is None:
        return None
    classes: dict[str, type[object]] = {
        "security": SecurityIdentityEvidence,
        "firm": FirmOntologyEvidence,
        "common_event": CommonEventIdentityEvidence,
        "sector": SectorClassificationEvidence,
        "control": PreopenControlEvidence,
        "q_data": DataQualityEvidence,
    }
    component_type = classes[name]
    expected = frozenset(
        field.name for field in dataclasses.fields(component_type)
    )
    raw = dict(_exact_fields(value, expected, f"C2 {name} evidence"))
    try:
        if name == "firm":
            raw["current_score"] = _fraction(
                raw["current_score"], "firm current_score"
            )
            raw["previous_score"] = _fraction(
                raw["previous_score"], "firm previous_score"
            )
        elif name == "q_data":
            encoded = raw["q_data"]
            if type(encoded) is not str:
                raise PhysicalProductionInputArchiveError(
                    "q_data is not canonical decimal text"
                )
            try:
                raw["q_data"] = Decimal(encoded)
            except InvalidOperation as exc:
                raise PhysicalProductionInputArchiveError(
                    "q_data is not canonical decimal text"
                ) from exc
        return component_type(**raw)
    except PhysicalProductionInputArchiveError:
        raise
    except (TypeError, ValueError) as exc:
        raise PhysicalProductionInputArchiveError(
            f"C2 {name} evidence is invalid"
        ) from exc


def _decode_evidence_record(value: object) -> ProductionRowEvidence:
    raw = _exact_fields(value, _EVIDENCE_FIELDS, "C2 evidence row")
    try:
        return ProductionRowEvidence(
            locator=_decode_locator(raw["locator"]),
            security=_construct_component("security", raw["security"]),
            firm=_construct_component("firm", raw["firm"]),
            common_event=_construct_component(
                "common_event", raw["common_event"]
            ),
            sector=_construct_component("sector", raw["sector"]),
            control=_construct_component("control", raw["control"]),
            q_data=_construct_component("q_data", raw["q_data"]),
        )
    except PhysicalProductionInputArchiveError:
        raise
    except (TypeError, ValueError) as exc:
        raise PhysicalProductionInputArchiveError(
            "C2 evidence row is invalid"
        ) from exc


def _decode_normalized_record(value: object) -> NormalizedPreOutcomeRow:
    raw = dict(_exact_fields(value, _NORMALIZED_FIELDS, "C2 normalized row"))
    try:
        raw["source_locator"] = _decode_locator(raw["source_locator"])
        raw["source_role"] = MassiveSourceRole(raw["source_role"])
        raw["signal_arm"] = SignalArm(raw["signal_arm"])
        for name in ("previous_score", "current_score", "rating_change"):
            raw[name] = _fraction(raw[name], f"normalized {name}")
        encoded_q = raw["q_data"]
        if type(encoded_q) is not str:
            raise PhysicalProductionInputArchiveError(
                "normalized q_data is not canonical decimal text"
            )
        raw["q_data"] = Decimal(encoded_q)
        return NormalizedPreOutcomeRow(**raw)
    except PhysicalProductionInputArchiveError:
        raise
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PhysicalProductionInputArchiveError(
            "C2 normalized row is invalid"
        ) from exc


def _validate_source_bindings(
    source_bindings: tuple[EvidenceSourceBinding, ...],
) -> None:
    if type(source_bindings) is not tuple or any(
        type(item) is not EvidenceSourceBinding for item in source_bindings
    ):
        raise PhysicalProductionInputArchiveError(
            "source bindings must be an exact typed tuple"
        )
    if tuple(item.kind for item in source_bindings) != _SOURCE_ORDER:
        raise PhysicalProductionInputArchiveError(
            "source bindings are not the closed canonical inventory"
        )
    try:
        for item in source_bindings:
            item.__post_init__()
    except ValueError as exc:
        raise PhysicalProductionInputArchiveError(
            "source binding is invalid"
        ) from exc


def _snapshot_source_bindings(
    source_bindings: tuple[EvidenceSourceBinding, ...],
) -> tuple[EvidenceSourceBinding, ...]:
    """Detach build authority from caller-held frozen-object mutation."""

    _require_static_contract()
    _validate_source_bindings(source_bindings)
    snapshot = tuple(
        _PINNED_SOURCE_BINDING_TYPE(
            kind=item.kind,
            artifact_id=item.artifact_id,
            artifact_sha256=item.artifact_sha256,
            reviewed=item.reviewed,
            point_in_time=item.point_in_time,
        )
        for item in source_bindings
    )
    _require_static_contract()
    _validate_source_bindings(snapshot)
    return snapshot


def _validate_component_bindings(
    row: ProductionRowEvidence,
    source_map: Mapping[EvidenceSourceKind, EvidenceSourceBinding],
) -> None:
    bindings = (
        (
            row.security,
            EvidenceSourceKind.SECURITY_MASTER,
            "security_master_id",
            "security_master_sha256",
        ),
        (
            row.firm,
            EvidenceSourceKind.FIRM_ONTOLOGY,
            "ontology_id",
            "ontology_sha256",
        ),
        (
            row.common_event,
            EvidenceSourceKind.COMMON_EVENT,
            "source_id",
            "source_sha256",
        ),
        (
            row.sector,
            EvidenceSourceKind.SECTOR_CLASSIFICATION,
            "source_id",
            "source_sha256",
        ),
        (
            row.control,
            EvidenceSourceKind.PREOPEN_CONTROL,
            "source_id",
            "source_sha256",
        ),
        (
            row.q_data,
            EvidenceSourceKind.DATA_QUALITY,
            "source_id",
            "source_sha256",
        ),
    )
    for component, kind, id_name, sha_name in bindings:
        if component is None:
            continue
        binding = source_map[kind]
        if (
            getattr(component, id_name) != binding.artifact_id
            or getattr(component, sha_name) != binding.artifact_sha256
        ):
            raise PhysicalProductionInputArchiveError(
                f"{kind.value} evidence source binding mismatch"
            )


def _locator_key(locator: CaptureRowLocator) -> tuple[int, int, int]:
    return locator.sort_key


def _encode_key(value: object) -> bytes:
    return _canonical_fragment(value)


def _open_spool(
    path: Path,
    *,
    root_path: Path,
    root_fd: int,
    stage_name: str,
    stage_fd: int,
    created_files: dict[str, tuple[int, int]],
) -> sqlite3.Connection:
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = os.open("spool.sqlite3", flags, 0o600, dir_fd=stage_fd)
    try:
        os.fchmod(descriptor, 0o600)
        metadata = os.fstat(descriptor)
        _require_private_regular_metadata(
            metadata, "physical C2 SQLite spool", allow_empty=True
        )
        spool_identity = _regular_inode_identity(metadata)
        created_files["spool.sqlite3"] = spool_identity
    finally:
        os.close(descriptor)
    _require_reopened_directory_identity(
        root_path, root_fd, "physical C2 archive root"
    )
    _require_pinned_child_identity(
        root_fd, stage_name, stage_fd, "physical C2 staging directory"
    )
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(path)
        _require_reopened_directory_identity(
            root_path, root_fd, "physical C2 archive root"
        )
        _require_pinned_child_identity(
            root_fd, stage_name, stage_fd, "physical C2 staging directory"
        )
        _require_created_file_identity_at(
            stage_fd,
            "spool.sqlite3",
            spool_identity,
            "physical C2 SQLite spool",
            allow_empty=True,
        )
        connection.executescript(
            """
        PRAGMA locking_mode=EXCLUSIVE;
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        PRAGMA temp_store=FILE;
        PRAGMA mmap_size=0;
        PRAGMA cache_size=-32768;
            """
        )
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        maximum_pages = MAX_SQLITE_BYTES // page_size
        if maximum_pages < 1:
            raise PhysicalProductionInputCapacityError(
                "C2 SQLite spool bound is smaller than one database page"
            )
        configured_pages = int(
            connection.execute(
                f"PRAGMA max_page_count={maximum_pages}"
            ).fetchone()[0]
        )
        if configured_pages != maximum_pages:
            raise PhysicalProductionInputCapacityError(
                "C2 SQLite spool hard page bound could not be installed"
            )
        connection.executescript(
            """
        CREATE TABLE evidence (
            role_ordinal INTEGER NOT NULL,
            page_number INTEGER NOT NULL,
            row_offset INTEGER NOT NULL,
            locator BLOB NOT NULL,
            record BLOB NOT NULL,
            matched INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(role_ordinal, page_number, row_offset)
        ) WITHOUT ROWID;
        CREATE TABLE facts (
            namespace TEXT NOT NULL,
            fact_key BLOB NOT NULL,
            fact_value BLOB NOT NULL,
            PRIMARY KEY(namespace, fact_key)
        ) WITHOUT ROWID;
        CREATE TABLE lineage (
            namespace TEXT NOT NULL,
            identifier TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            valid_to TEXT NOT NULL,
            identity_value BLOB NOT NULL,
            PRIMARY KEY(
                namespace, identifier, valid_from, valid_to, identity_value
            )
        ) WITHOUT ROWID;
        CREATE TABLE comparison (
            dimension_ordinal INTEGER NOT NULL,
            dimension TEXT NOT NULL,
            comparison_key TEXT NOT NULL,
            total_count INTEGER NOT NULL,
            current_admitted_count INTEGER NOT NULL,
            censored_admitted_count INTEGER NOT NULL,
            mapping_disagreement_count INTEGER NOT NULL,
            signal_disagreement_count INTEGER NOT NULL,
            PRIMARY KEY(dimension_ordinal, comparison_key)
        ) WITHOUT ROWID;
            """
        )
        _require_reopened_directory_identity(
            root_path, root_fd, "physical C2 archive root"
        )
        _require_pinned_child_identity(
            root_fd, stage_name, stage_fd, "physical C2 staging directory"
        )
        _require_created_file_identity_at(
            stage_fd,
            "spool.sqlite3",
            spool_identity,
            "physical C2 SQLite spool",
        )
        return connection
    except BaseException:
        if connection is not None:
            connection.close()
        raise


def _spool_bytes(connection: sqlite3.Connection) -> int:
    page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
    page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
    return page_count * page_size


def _check_spool_bound(connection: sqlite3.Connection) -> None:
    if _spool_bytes(connection) > MAX_SQLITE_BYTES:
        raise PhysicalProductionInputCapacityError(
            "C2 SQLite spool exceeds its fixed byte bound"
        )


def _is_sqlite_full(error: BaseException) -> bool:
    """Recognize SQLite's hard-page-ceiling refusal without masking peers."""

    if not isinstance(error, sqlite3.OperationalError):
        return False
    error_code = getattr(error, "sqlite_errorcode", None)
    if type(error_code) is int and (
        error_code & 0xFF
    ) == sqlite3.SQLITE_FULL:
        return True
    return str(error).casefold() == "database or disk is full"


def _remember_fact(
    connection: sqlite3.Connection,
    namespace: str,
    key: tuple[object, ...],
    value: tuple[object, ...],
) -> None:
    encoded_key = _encode_key(list(key))
    encoded_value = _encode_key(list(value))
    prior = connection.execute(
        "SELECT fact_value FROM facts WHERE namespace=? AND fact_key=?",
        (namespace, encoded_key),
    ).fetchone()
    if prior is None:
        connection.execute(
            "INSERT INTO facts(namespace, fact_key, fact_value) VALUES (?, ?, ?)",
            (namespace, encoded_key, encoded_value),
        )
    elif bytes(prior[0]) != encoded_value:
        raise PhysicalProductionInputArchiveError(
            f"conflicting cross-row {namespace} evidence"
        )


def _add_lineage(
    connection: sqlite3.Connection,
    *,
    namespace: str,
    identifier: str,
    valid_from: str,
    valid_to: str | None,
    identity: tuple[str, ...],
) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO lineage(namespace, identifier, valid_from, "
        "valid_to, identity_value) VALUES (?, ?, ?, ?, ?)",
        (
            namespace,
            identifier,
            valid_from,
            "" if valid_to is None else valid_to,
            _encode_key(list(identity)),
        ),
    )


def _accumulate_topology(
    connection: sqlite3.Connection,
    source: AcceptedRiskSourceRow,
    item: ProductionRowEvidence,
) -> None:
    session = source.current_view.eligible_session
    if source.event_date is None or session is None:
        raise PhysicalProductionInputArchiveError(
            "candidate row evidence has no event or eligibility session"
        )
    security = item.security
    if security is not None:
        security_fact = (
            security.historical_ticker,
            security.issuer_id,
            security.share_class_id,
            security.listing_id,
            security.security_master_id,
            security.security_master_sha256,
            security.mapping_version_id,
            security.mapping_evidence_sha256,
            security.valid_from,
            security.valid_to,
            security.valid_to_available_at,
            security.available_at,
            security.candidate_count,
            security.point_in_time,
            security.current_ticker_only,
        )
        _remember_fact(
            connection,
            "security/session",
            (security.security_id, session),
            security_fact,
        )
        _remember_fact(
            connection,
            "source-ticker/date identity",
            (security.source_current_restated_ticker, source.event_date),
            (security.security_id, *security_fact),
        )
        permanent_identity = (
            security.security_id,
            security.issuer_id,
            security.share_class_id,
            security.listing_id,
            security.security_master_id,
            security.security_master_sha256,
        )
        lineage = (
            (
                "security_id",
                security.security_id,
                (
                    security.historical_ticker,
                    security.issuer_id,
                    security.share_class_id,
                    security.listing_id,
                    security.security_master_id,
                    security.security_master_sha256,
                ),
            ),
            ("historical_ticker", security.historical_ticker, permanent_identity),
            (
                "source_current_restated_ticker",
                security.source_current_restated_ticker,
                permanent_identity,
            ),
            (
                "listing_id",
                security.listing_id,
                (
                    security.security_id,
                    security.issuer_id,
                    security.share_class_id,
                    security.security_master_id,
                    security.security_master_sha256,
                ),
            ),
        )
        for namespace, identifier, identity in lineage:
            _add_lineage(
                connection,
                namespace=f"security {namespace} lineage",
                identifier=identifier,
                valid_from=security.valid_from,
                valid_to=security.valid_to,
                identity=identity,
            )
    firm = item.firm
    if firm is not None:
        _remember_fact(
            connection,
            "firm/date ontology",
            (firm.provider_firm_id, source.event_date),
            (
                firm.institution_id,
                firm.ontology_id,
                firm.ontology_sha256,
                firm.valid_from,
                firm.valid_to,
                firm.valid_to_available_at,
                firm.available_at,
                firm.candidate_count,
                firm.ontology_reviewed,
            ),
        )
        _remember_fact(
            connection,
            "firm/rating-scale/date",
            (
                firm.provider_firm_id,
                firm.raw_current_label.casefold(),
                firm.raw_previous_label.casefold(),
                source.event_date,
            ),
            (
                firm.institution_id,
                [firm.current_score.numerator, firm.current_score.denominator],
                [firm.previous_score.numerator, firm.previous_score.denominator],
                firm.ontology_entry_sha256,
                firm.labels_reviewed,
            ),
        )
        _add_lineage(
            connection,
            namespace="provider-firm identity lineage",
            identifier=firm.provider_firm_id,
            valid_from=firm.valid_from,
            valid_to=firm.valid_to,
            identity=(firm.institution_id, firm.ontology_id, firm.ontology_sha256),
        )
    common = item.common_event
    if common is not None:
        _remember_fact(
            connection,
            "common-event identity",
            (common.common_event_id,),
            (
                common.source_id,
                common.source_sha256,
                common.evidence_sha256,
                common.available_at,
                common.candidate_count,
            ),
        )
    sector = item.sector
    if sector is not None:
        _remember_fact(
            connection,
            "sector/security/session",
            (sector.security_id, session),
            (
                sector.sector_id,
                sector.source_id,
                sector.source_sha256,
                sector.evidence_sha256,
                sector.valid_from,
                sector.valid_to,
                sector.valid_to_available_at,
                sector.available_at,
                sector.candidate_count,
                sector.point_in_time,
            ),
        )
    control = item.control
    if control is not None:
        _remember_fact(
            connection,
            "control/security/session",
            (control.security_id, control.decision_session),
            (
                control.industry_id,
                control.source_id,
                control.source_sha256,
                control.evidence_sha256,
                control.available_at,
                control.control_vector_sha256,
                control.complete,
                control.point_in_time,
                control.contains_outcome_or_price,
            ),
        )
    quality = item.q_data
    if quality is not None:
        quality_numerator, quality_denominator = quality.q_data.as_integer_ratio()
        _remember_fact(
            connection,
            "q_data/security/session",
            (quality.security_id, quality.measured_session),
            (
                quality.source_id,
                quality.source_sha256,
                quality.evidence_sha256,
                quality.available_at,
                quality.measurement_method_id,
                quality_numerator,
                quality_denominator,
                quality.point_in_time,
            ),
        )


def _validate_lineage(connection: sqlite3.Connection) -> None:
    cursor = connection.execute(_LINEAGE_SCAN_SQL)
    active_group: tuple[str, str] | None = None
    active_identity: bytes | None = None
    active_end: str | None = None
    for namespace, identifier, valid_from, valid_to, identity_value in cursor:
        group = (str(namespace), str(identifier))
        if group != active_group:
            active_group = group
            active_identity = None
            active_end = None
        identity = bytes(identity_value)
        start = str(valid_from)
        end = None if valid_to == "" else str(valid_to)
        if (
            active_identity is not None
            and active_end is not None
            and active_end <= start
        ):
            active_identity = None
            active_end = None
        if active_identity is not None and active_identity != identity:
            raise PhysicalProductionInputArchiveError(
                f"contradictory overlapping {namespace} evidence"
            )
        if active_identity is None:
            active_identity = identity
            active_end = end
        elif active_end is not None and (end is None or end > active_end):
            active_end = end


def _comparison_keys(
    source: AcceptedRiskSourceRow,
    evidence: ProductionRowEvidence | None,
) -> tuple[tuple[int, str, str], ...]:
    values = {
        ComparisonDimension.OVERALL: "all_rows",
        ComparisonDimension.EVENT_YEAR: (
            str(source.event_year)
            if source.event_year is not None
            else "__invalid_event_year__"
        ),
        ComparisonDimension.ACTION: source.action_label,
        ComparisonDimension.FIRM: (
            evidence.firm.institution_id
            if evidence is not None and evidence.firm is not None
            else f"unmapped:{source.firm_label}"
        ),
        ComparisonDimension.SECURITY: (
            evidence.security.security_id
            if evidence is not None and evidence.security is not None
            else f"unmapped:{source.current_restated_security_label}"
        ),
    }
    return tuple(
        (ordinal, dimension.value, values[dimension])
        for ordinal, dimension in enumerate(ComparisonDimension)
    )


def _accumulate_comparison(
    connection: sqlite3.Connection,
    source: AcceptedRiskSourceRow,
    evidence: ProductionRowEvidence | None,
    current: object,
    censored: object,
) -> None:
    current_admitted = int(current.normalized_row is not None)
    censored_admitted = int(censored.normalized_row is not None)
    mapping_disagreement = int(
        _PINNED_MAPPING_SIGNATURE(current) != _PINNED_MAPPING_SIGNATURE(censored)
    )
    signal_disagreement = int(
        _PINNED_SIGNAL_SIGNATURE(current) != _PINNED_SIGNAL_SIGNATURE(censored)
    )
    for ordinal, dimension, key in _comparison_keys(source, evidence):
        connection.execute(
            """
            INSERT INTO comparison(
                dimension_ordinal, dimension, comparison_key, total_count,
                current_admitted_count, censored_admitted_count,
                mapping_disagreement_count, signal_disagreement_count
            ) VALUES (?, ?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(dimension_ordinal, comparison_key) DO UPDATE SET
                total_count=total_count+1,
                current_admitted_count=current_admitted_count+excluded.current_admitted_count,
                censored_admitted_count=censored_admitted_count+excluded.censored_admitted_count,
                mapping_disagreement_count=mapping_disagreement_count+excluded.mapping_disagreement_count,
                signal_disagreement_count=signal_disagreement_count+excluded.signal_disagreement_count
            """,
            (
                ordinal,
                dimension,
                key,
                current_admitted,
                censored_admitted,
                mapping_disagreement,
                signal_disagreement,
            ),
        )


def _comparison_record(raw: tuple[object, ...]) -> dict[str, object]:
    (
        _ordinal,
        dimension,
        key,
        total,
        current_admitted,
        censored_admitted,
        mapping_disagreement,
        signal_disagreement,
    ) = raw
    values = {
        "current_admitted": int(current_admitted),
        "current_refused": int(total) - int(current_admitted),
        "censored_admitted": int(censored_admitted),
        "censored_refused": int(total) - int(censored_admitted),
        "mapping_disagreement": int(mapping_disagreement),
        "signal_disagreement": int(signal_disagreement),
    }
    result: dict[str, object] = {
        "dimension": dimension,
        "key": key,
        "total_count": total,
    }
    for name, count in values.items():
        result[f"{name}_count"] = count
        result[f"{name}_rate"] = {
            "numerator": count,
            "denominator": total,
        }
    return result


def _iter_comparison_records(connection: sqlite3.Connection) -> Iterator[bytes]:
    cursor = connection.execute(
        "SELECT dimension_ordinal, dimension, comparison_key, total_count, "
        "current_admitted_count, censored_admitted_count, "
        "mapping_disagreement_count, signal_disagreement_count "
        "FROM comparison ORDER BY dimension_ordinal, comparison_key"
    )
    for raw in cursor:
        yield _canonical_fragment(_comparison_record(tuple(raw)))


def _report_semantic_fields(
    connection: sqlite3.Connection,
    *,
    pair_id: str,
    pair_sha256: str,
) -> dict[str, object]:
    return {
        "schema": _c2.COMPARISON_REPORT_SCHEMA,
        "pair_id": pair_id,
        "pair_sha256": pair_sha256,
        "breakdowns": _JsonArray(lambda: _iter_comparison_records(connection)),
        "exhaustive": True,
        "pre_return": True,
        "outcome_access": False,
    }


def _authority_fields(
    *,
    pair_id: str,
    pair_sha256: str,
    sources: tuple[EvidenceSourceBinding, ...],
    evidence_items: Callable[[], Iterator[bytes]],
) -> dict[str, object]:
    return {
        "schema": _c2.PRODUCTION_EVIDENCE_SCHEMA,
        "status": _c2.PRODUCTION_INPUT_STATUS,
        "contract_id": _c2.PRODUCTION_INPUT_CONTRACT_ID,
        "contract_sha256": _c2.PRODUCTION_INPUT_CONTRACT_SHA256,
        "pair_id": pair_id,
        "pair_sha256": pair_sha256,
        "source_bindings": [item.to_record() for item in sources],
        "row_evidence": _JsonArray(evidence_items),
        "pristine_point_in_time": False,
        "current_ticker_identity_allowed": False,
        "production_registry_receipt": None,
        "production_truth_approval": None,
        "outcome_authority": None,
        "capabilities": {
            "provider_access": False,
            "credential_access": False,
            "filesystem_access": False,
            "quantconnect_access": False,
            "object_store_access": False,
            "price_access": False,
            "outcome_access": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        },
    }


def _package_fields(
    *,
    pair_id: str,
    pair_sha256: str,
    sources: tuple[EvidenceSourceBinding, ...],
    evidence_items: Callable[[], Iterator[bytes]],
    evidence_row_count: int,
    component_counts: tuple[tuple[str, int], ...],
    source_projection_sha256: str,
    row_projection_sha256: str,
) -> dict[str, object]:
    return {
        "schema": PACKAGE_SCHEMA,
        "pair_id": pair_id,
        "pair_sha256": pair_sha256,
        "source_bindings": [item.to_record() for item in sources],
        "row_evidence": _JsonArray(evidence_items),
        "source_count": len(sources),
        "row_count": evidence_row_count,
        "component_present_counts": [
            {"kind": kind, "present_count": count}
            for kind, count in component_counts
        ],
        "source_projection_sha256": source_projection_sha256,
        "row_projection_sha256": row_projection_sha256,
    }


def _batch_fields(
    *,
    evidence_authority_id: str,
    evidence_authority_sha256: str,
    pair_id: str,
    pair_sha256: str,
    arm: SignalArm,
    total_source_row_count: int,
    source_view_included_count: int,
    directional_candidate_count: int,
    normalized_row_count: int,
    admission_items: Callable[[], Iterator[bytes]],
    normalized_items: Callable[[], Iterator[bytes]],
    comparison_report_chunks: Callable[[], Iterator[bytes]],
) -> dict[str, object]:
    return {
        "schema": _c2.PRODUCTION_INPUT_BATCH_SCHEMA,
        "status": _c2.PRODUCTION_INPUT_STATUS,
        "contract_id": _c2.PRODUCTION_INPUT_CONTRACT_ID,
        "contract_sha256": _c2.PRODUCTION_INPUT_CONTRACT_SHA256,
        "evidence_authority_id": evidence_authority_id,
        "evidence_authority_sha256": evidence_authority_sha256,
        "pair_id": pair_id,
        "pair_sha256": pair_sha256,
        "signal_arm": arm.value,
        "source_view": _ARM_TO_VIEW[arm].value,
        "source_view_label": _ARM_TO_LABEL[arm],
        "non_pristine_disclosure": _c2.NON_PRISTINE_DISCLOSURE,
        "total_source_row_count": total_source_row_count,
        "source_view_included_count": source_view_included_count,
        "directional_candidate_count": directional_candidate_count,
        "normalized_row_count": normalized_row_count,
        "refused_directional_count": (
            directional_candidate_count - normalized_row_count
        ),
        "admissions": _JsonArray(admission_items),
        "normalized_rows": _JsonArray(normalized_items),
        "comparison_report": _RawJson(comparison_report_chunks),
        "exhaustive_source_census": True,
        "source_role_separate_from_signal_arm": True,
        "event_level_only": True,
        "decision_date_cross_sections_required": True,
        "decision_date_cross_sections_bound": False,
        "pristine_point_in_time": False,
        "earlier_version_imputation_performed": False,
        "production_input_authority": False,
        "formal_backtest_input_ready": False,
        "external_bindings": {
            "production_registry_receipt": None,
            "production_truth_approval": None,
            "outcome_authority": None,
        },
        "capabilities": {
            "provider_access": False,
            "credential_access": False,
            "filesystem_access": False,
            "quantconnect_access": False,
            "object_store_access": False,
            "price_access": False,
            "outcome_access": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        },
    }


def _manifest_semantic_record(
    *,
    parent_archive_id: str,
    parent_archive_sha256: str,
    fixture_only: bool,
    pair_id: str,
    pair_sha256: str,
    evidence_authority_id: str,
    evidence_authority_sha256: str,
    source_bindings: tuple[EvidenceSourceBinding, ...],
    source_projection_sha256: str,
    row_projection_sha256: str,
    evidence_row_count: int,
    component_present_counts: tuple[tuple[str, int], ...],
    evidence_rows: PhysicalC2FileDescriptor,
    evidence_package: PhysicalC2FileDescriptor,
    comparison_report: PhysicalC2FileDescriptor,
    comparison_report_sha256: str,
    batches: tuple[PhysicalProductionInputBatchArchive, ...],
) -> dict[str, object]:
    return {
        "schema": ARCHIVE_SCHEMA,
        "parent_archive_id": parent_archive_id,
        "parent_archive_sha256": parent_archive_sha256,
        "fixture_only": fixture_only,
        "pair_id": pair_id,
        "pair_sha256": pair_sha256,
        "evidence_authority_id": evidence_authority_id,
        "evidence_authority_sha256": evidence_authority_sha256,
        "source_bindings": [item.to_record() for item in source_bindings],
        "source_projection_sha256": source_projection_sha256,
        "row_projection_sha256": row_projection_sha256,
        "evidence_row_count": evidence_row_count,
        "component_present_counts": [
            {"kind": kind, "present_count": count}
            for kind, count in component_present_counts
        ],
        "files": [
            evidence_rows.to_record(),
            evidence_package.to_record(),
            comparison_report.to_record(),
            *(
                descriptor.to_record()
                for batch in batches
                for descriptor in (batch.admissions, batch.normalized_rows)
            ),
        ],
        "comparison_report_sha256": comparison_report_sha256,
        "batches": [item.to_record() for item in batches],
        "maximum_source_row_count": MAX_SOURCE_ROWS,
        "maximum_evidence_row_count": MAX_EVIDENCE_ROWS,
        "retention": {
            "full_pair_materialized": False,
            "full_evidence_materialized": False,
            "full_admission_census_materialized": False,
        },
        "capabilities": {
            "provider_access": False,
            "credential_access": False,
            "quantconnect_access": False,
            "outcome_access": False,
            "result_access": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        },
    }


def _require_static_contract() -> None:
    try:
        changed = (
            _c2._require_static_contract is not _PINNED_REQUIRE_STATIC_CONTRACT
            or _c2._admit_source_row is not _PINNED_ADMIT_SOURCE_ROW
            or _c2._mapping_signature is not _PINNED_MAPPING_SIGNATURE
            or _c2._signal_signature is not _PINNED_SIGNAL_SIGNATURE
            or tuple(EvidenceSourceKind) != _SOURCE_ORDER
            or tuple(SignalArm) != _ARM_ORDER
            or any(
                _c2._ARM_TO_VIEW[arm] is not _ARM_TO_VIEW[arm]
                for arm in _ARM_ORDER
            )
            or any(
                _c2._ARM_TO_LABEL[arm] != _ARM_TO_LABEL[arm]
                for arm in _ARM_ORDER
            )
            or _c1_disk.PhysicalAcceptedRiskArchive
            is not _PINNED_C1_ARCHIVE_TYPE
            or _c1_disk.require_physical_accepted_risk_archive
            is not _PINNED_REQUIRE_C1_ARCHIVE
            or _c1_disk.iter_physical_accepted_risk_rows
            is not _PINNED_ITER_C1_ROWS
            or _c1_disk._massive is not _PINNED_C1_MASSIVE_MODULE
            or type(_c1_disk._massive.PRODUCTION_TRANSPORT) is not str
            or _c1_disk._massive.PRODUCTION_TRANSPORT
            is not _PINNED_PRODUCTION_C1_TRANSPORT
            or _c1_disk._massive.PRODUCTION_TRANSPORT
            != _PINNED_PRODUCTION_C1_TRANSPORT
            or _c1_disk._massive.REPOSITORY_ARTIFACTS_ROOT
            is not _PINNED_REPOSITORY_ARTIFACTS_ROOT
            or AcceptedRiskSourceRow is not _PINNED_SOURCE_ROW_TYPE
            or AcceptedRiskSourceRow.__post_init__
            is not _PINNED_SOURCE_ROW_POST_INIT
            or CaptureRowLocator is not _PINNED_LOCATOR_TYPE
            or CaptureRowLocator.to_record is not _PINNED_LOCATOR_TO_RECORD
            or EvidenceSourceBinding is not _PINNED_SOURCE_BINDING_TYPE
            or EvidenceSourceBinding.__post_init__
            is not _PINNED_SOURCE_BINDING_POST_INIT
            or EvidenceSourceBinding.to_record
            is not _PINNED_SOURCE_BINDING_TO_RECORD
            or ProductionRowEvidence is not _PINNED_EVIDENCE_ROW_TYPE
            or ProductionRowEvidence.__post_init__
            is not _PINNED_EVIDENCE_ROW_POST_INIT
            or ProductionRowEvidence.to_record
            is not _PINNED_EVIDENCE_ROW_TO_RECORD
            or (
                SecurityIdentityEvidence,
                FirmOntologyEvidence,
                CommonEventIdentityEvidence,
                SectorClassificationEvidence,
                PreopenControlEvidence,
                DataQualityEvidence,
            )
            != _PINNED_COMPONENT_TYPES
            or tuple(
                component_type.__post_init__
                for component_type in _PINNED_COMPONENT_TYPES
            )
            != _PINNED_COMPONENT_POST_INITS
            or tuple(
                component_type.to_record
                for component_type in _PINNED_COMPONENT_TYPES
            )
            != _PINNED_COMPONENT_TO_RECORDS
            or _NATIVE_RENAME_NOREPLACE
            is not _PINNED_NATIVE_RENAME_NOREPLACE
            or _NATIVE_RENAME_NOREPLACE_FLAG
            is not _PINNED_NATIVE_RENAME_NOREPLACE_FLAG
            or _NATIVE_RENAME_NOREPLACE_FLAG
            != _PINNED_NATIVE_RENAME_NOREPLACE_FLAG
            or (
                _NATIVE_RENAME_NOREPLACE is not None
                and tuple(_NATIVE_RENAME_NOREPLACE.argtypes)
                != _PINNED_NATIVE_RENAME_ARGTYPES
            )
            or (
                _NATIVE_RENAME_NOREPLACE is not None
                and _NATIVE_RENAME_NOREPLACE.restype
                is not _PINNED_NATIVE_RENAME_RESTYPE
            )
            or ctypes.get_errno is not _PINNED_CTYPES_GET_ERRNO
            or ctypes.set_errno is not _PINNED_CTYPES_SET_ERRNO
            or _PINNED_NATIVE_RENAME_NOREPLACE is None
            or type(_PINNED_NATIVE_RENAME_NOREPLACE_FLAG) is not int
            or AcceptedRiskPairBinding is not _PINNED_ACCEPTED_RISK_BINDING_TYPE
            or require_accepted_risk_pair_binding
            is not _PINNED_REQUIRE_ACCEPTED_RISK_BINDING
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        changed = True
    if changed:
        raise PhysicalProductionInputArchiveError(
            "physical C2 static contract changed"
        )
    try:
        _PINNED_REQUIRE_STATIC_CONTRACT()
    except ValueError as exc:
        raise PhysicalProductionInputArchiveError(
            "production input contract is not current"
        ) from exc


def _source_projection(source_bindings: tuple[EvidenceSourceBinding, ...]) -> str:
    return sha256_bytes(
        canonical_json_bytes(
            {
                "schema": SOURCE_PROJECTION_SCHEMA,
                "sources": [item.to_record() for item in source_bindings],
            }
        )
    )


def _row_projection_at(
    stage_fd: int,
    descriptor: PhysicalC2FileDescriptor,
) -> str:
    fields = {
        "schema": ROW_PROJECTION_SCHEMA,
        "rows": _JsonArray(
            lambda: _iter_jsonl_fragments_at(
                stage_fd, descriptor.relative_path, descriptor
            )
        ),
    }
    _count, digest = _digest_chunks(
        _iter_canonical_object(fields, terminate=True)
    )
    return digest


def _evidence_for_source(
    connection: sqlite3.Connection,
    source: AcceptedRiskSourceRow,
) -> ProductionRowEvidence | None:
    key = source.locator.sort_key
    result = connection.execute(
        "SELECT locator, record FROM evidence WHERE role_ordinal=? "
        "AND page_number=? AND row_offset=?",
        key,
    ).fetchone()
    if result is None:
        return None
    locator_payload = bytes(result[0])
    expected_locator = _canonical_fragment(source.locator.to_record())
    if locator_payload != expected_locator:
        raise PhysicalProductionInputArchiveError(
            "evidence locator identity differs from its C1 source row"
        )
    evidence = _decode_evidence_record(
        _strict_record(bytes(result[1]), "spooled C2 evidence row")
    )
    if evidence.locator != source.locator:
        raise PhysicalProductionInputArchiveError(
            "evidence locator changed during disk round trip"
        )
    if (
        source.locator.source_role is not MassiveSourceRole.ANALYST_RATINGS
        or not source.current_view.included
    ):
        raise PhysicalProductionInputArchiveError(
            "row evidence targets an excluded or non-rating C1 source locator"
        )
    connection.execute(
        "UPDATE evidence SET matched=1 WHERE role_ordinal=? "
        "AND page_number=? AND row_offset=?",
        key,
    )
    _accumulate_topology(connection, source, evidence)
    return evidence


def _spool_evidence(
    connection: sqlite3.Connection,
    writer: _PrivateJsonlWriter,
    *,
    evidence_rows: Iterable[ProductionRowEvidence],
    source_map: Mapping[EvidenceSourceKind, EvidenceSourceBinding],
    require_live: Callable[[], None],
) -> tuple[int, tuple[tuple[str, int], ...]]:
    previous_key: tuple[int, int, int] | None = None
    counts = {name: 0 for name in _COMPONENT_NAMES}
    count = 0
    try:
        iterator = iter(evidence_rows)
    except TypeError as exc:
        raise PhysicalProductionInputArchiveError(
            "row evidence must be an iterable of exact evidence rows"
        ) from exc
    while True:
        _require_static_contract()
        require_live()
        try:
            item = next(iterator)
        except StopIteration:
            _require_static_contract()
            require_live()
            break
        _require_static_contract()
        require_live()
        if type(item) is not _PINNED_EVIDENCE_ROW_TYPE:
            raise PhysicalProductionInputArchiveError(
                "row evidence iterator yielded the wrong type"
            )
        try:
            _PINNED_EVIDENCE_ROW_POST_INIT(item)
        except ValueError as exc:
            raise PhysicalProductionInputArchiveError(
                "row evidence failed its exact component contract"
            ) from exc
        record = _PINNED_EVIDENCE_ROW_TO_RECORD(item)
        payload = _canonical_fragment(record)
        persisted = _decode_evidence_record(
            _strict_record(payload, "serialized C2 evidence row")
        )
        persisted_record = _PINNED_EVIDENCE_ROW_TO_RECORD(persisted)
        if _canonical_fragment(persisted_record) != payload:
            raise PhysicalProductionInputArchiveError(
                "serialized C2 evidence row changed during exact decoding"
            )
        _validate_component_bindings(persisted, source_map)
        for name in _COMPONENT_NAMES:
            if getattr(persisted, name) is not None:
                counts[name] += 1
        key = _locator_key(persisted.locator)
        if previous_key is not None and key <= previous_key:
            raise PhysicalProductionInputArchiveError(
                "row evidence is not unique canonical source order"
            )
        previous_key = key
        try:
            connection.execute(
                "INSERT INTO evidence(role_ordinal, page_number, row_offset, "
                "locator, record) VALUES (?, ?, ?, ?, ?)",
                (
                    *key,
                    _canonical_fragment(
                        _PINNED_LOCATOR_TO_RECORD(persisted.locator)
                    ),
                    payload,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise PhysicalProductionInputArchiveError(
                "duplicate evidence locator"
            ) from exc
        writer.write_record(persisted_record)
        count += 1
        if count > MAX_EVIDENCE_ROWS:
            raise PhysicalProductionInputCapacityError(
                "evidence row count exceeds its fixed bound"
            )
        if count % SPOOL_BOUND_CHECK_INTERVAL == 0:
            _check_spool_bound(connection)
            require_live()
    connection.commit()
    _check_spool_bound(connection)
    require_live()
    return count, tuple((name, counts[name]) for name in _COMPONENT_NAMES)


def _build_physical_archive(
    *,
    accepted_risk_archive: object | None,
    parent_archive_id: str,
    parent_archive_sha256: str,
    fixture_only: bool,
    pair_id: str,
    pair_sha256: str,
    expected_source_row_count: int,
    expected_current_included_count: int | None,
    expected_censored_included_count: int | None,
    source_rows: Callable[[], Iterator[AcceptedRiskSourceRow]],
    source_bindings: tuple[EvidenceSourceBinding, ...],
    row_evidence: Iterable[ProductionRowEvidence],
    archive_root: Path,
) -> PhysicalProductionInputArchive:
    _require_static_contract()
    if not isinstance(archive_root, Path):
        raise PhysicalProductionInputArchiveError("archive_root must be a Path")
    root = archive_root.absolute()
    source_bindings = _snapshot_source_bindings(source_bindings)
    source_binding_bytes = canonical_json_bytes(
        [_PINNED_SOURCE_BINDING_TO_RECORD(item) for item in source_bindings]
    )
    try:
        require_identifier(parent_archive_id, "parent_archive_id")
        require_sha256(parent_archive_sha256, "parent_archive_sha256")
        require_identifier(pair_id, "pair_id")
        require_sha256(pair_sha256, "pair_sha256")
        require_int(
            expected_source_row_count,
            "expected_source_row_count",
            minimum=1,
        )
    except ValueError as exc:
        raise PhysicalProductionInputArchiveError(
            "physical C1 lineage is malformed"
        ) from exc
    if expected_source_row_count > MAX_SOURCE_ROWS:
        raise PhysicalProductionInputCapacityError(
            "C1 source row count exceeds the fixed C2 bound"
        )
    root, root_fd = _open_directory_path(
        root, name="physical C2 archive root"
    )
    try:
        stage_name, stage_fd = _create_private_stage_at(root_fd)
    except BaseException:
        os.close(root_fd)
        raise
    stage = root / stage_name
    spool = stage / "spool.sqlite3"
    created_files: dict[str, tuple[int, int]] = {}
    connection: sqlite3.Connection | None = None
    writers: list[_PrivateJsonlWriter] = []
    published = False
    preserve_staging = False
    publication_ambiguous = False
    registered_identity: int | None = None
    try:
        connection = _open_spool(
            spool,
            root_path=root,
            root_fd=root_fd,
            stage_name=stage_name,
            stage_fd=stage_fd,
            created_files=created_files,
        )
        evidence_writer = _PrivateJsonlWriter(
            stage_fd,
            EVIDENCE_ROWS,
            "row_evidence",
            created_files,
        )
        writers.append(evidence_writer)
        source_map = {item.kind: item for item in source_bindings}
        require_build_directories_live = lambda: _require_build_directories_live(
            root_path=root,
            root_fd=root_fd,
            stage_name=stage_name,
            stage_fd=stage_fd,
        )
        evidence_count, component_counts = _spool_evidence(
            connection,
            evidence_writer,
            evidence_rows=row_evidence,
            source_map=source_map,
            require_live=require_build_directories_live,
        )
        evidence_descriptor = evidence_writer.finish()

        current_admission_writer = _PrivateJsonlWriter(
            stage_fd,
            CURRENT_ADMISSIONS,
            "current_admissions",
            created_files,
        )
        current_normalized_writer = _PrivateJsonlWriter(
            stage_fd,
            CURRENT_NORMALIZED,
            "current_normalized_rows",
            created_files,
        )
        censored_admission_writer = _PrivateJsonlWriter(
            stage_fd,
            CENSORED_ADMISSIONS,
            "censored_admissions",
            created_files,
        )
        censored_normalized_writer = _PrivateJsonlWriter(
            stage_fd,
            CENSORED_NORMALIZED,
            "censored_normalized_rows",
            created_files,
        )
        writers.extend(
            (
                current_admission_writer,
                current_normalized_writer,
                censored_admission_writer,
                censored_normalized_writer,
            )
        )
        admission_writers = {
            SignalArm.CURRENT_VINTAGE: current_admission_writer,
            SignalArm.CONSERVATIVE_CENSORED: censored_admission_writer,
        }
        normalized_writers = {
            SignalArm.CURRENT_VINTAGE: current_normalized_writer,
            SignalArm.CONSERVATIVE_CENSORED: censored_normalized_writer,
        }
        source_count = 0
        included_counts = {arm: 0 for arm in _ARM_ORDER}
        directional_counts = {arm: 0 for arm in _ARM_ORDER}
        normalized_counts = {arm: 0 for arm in _ARM_ORDER}
        previous_locator: tuple[int, int, int] | None = None
        source_iterator = iter(source_rows())
        while True:
            _require_static_contract()
            require_build_directories_live()
            try:
                source = next(source_iterator)
            except StopIteration:
                _require_static_contract()
                require_build_directories_live()
                break
            _require_static_contract()
            require_build_directories_live()
            if type(source) is not _PINNED_SOURCE_ROW_TYPE:
                raise PhysicalProductionInputArchiveError(
                    "physical C1 iterator yielded the wrong row type"
                )
            try:
                _PINNED_SOURCE_ROW_POST_INIT(source)
            except ValueError as exc:
                raise PhysicalProductionInputArchiveError(
                    "physical C1 iterator yielded an invalid source row"
                ) from exc
            key = source.locator.sort_key
            if previous_locator is not None and key <= previous_locator:
                raise PhysicalProductionInputArchiveError(
                    "physical C1 rows are not unique canonical pair order"
                )
            previous_locator = key
            evidence = _evidence_for_source(connection, source)
            admissions: dict[SignalArm, object] = {}
            for arm in _ARM_ORDER:
                admission = _PINNED_ADMIT_SOURCE_ROW(
                    source=source,
                    evidence=evidence,
                    sources=source_map,
                    arm=arm,
                )
                admission.__post_init__()
                admissions[arm] = admission
                admission_writers[arm].write_record(admission.to_record())
                directional_counts[arm] += int(admission.potential_directional)
                normalized = admission.normalized_row
                if normalized is not None:
                    normalized.__post_init__()
                    normalized_writers[arm].write_record(normalized.to_record())
                    normalized_counts[arm] += 1
                view = (
                    source.current_view
                    if arm is SignalArm.CURRENT_VINTAGE
                    else source.censored_view
                )
                included_counts[arm] += int(view.included)
            _accumulate_comparison(
                connection,
                source,
                evidence,
                admissions[SignalArm.CURRENT_VINTAGE],
                admissions[SignalArm.CONSERVATIVE_CENSORED],
            )
            source_count += 1
            if source_count > MAX_SOURCE_ROWS:
                raise PhysicalProductionInputCapacityError(
                    "physical C1 traversal exceeds its fixed row bound"
                )
            if source_count % SPOOL_BOUND_CHECK_INTERVAL == 0:
                connection.commit()
                _check_spool_bound(connection)
                require_build_directories_live()
        connection.commit()
        require_build_directories_live()
        if source_count != expected_source_row_count:
            raise PhysicalProductionInputArchiveError(
                "physical C1 traversal count differs from its authority"
            )
        if (
            expected_current_included_count is not None
            and included_counts[SignalArm.CURRENT_VINTAGE]
            != expected_current_included_count
        ) or (
            expected_censored_included_count is not None
            and included_counts[SignalArm.CONSERVATIVE_CENSORED]
            != expected_censored_included_count
        ):
            raise PhysicalProductionInputArchiveError(
                "physical C1 inclusion census changed during C2 derivation"
            )
        unmatched = int(
            connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE matched=0"
            ).fetchone()[0]
        )
        if unmatched:
            raise PhysicalProductionInputArchiveError(
                "row evidence does not belong to the physical C1 archive"
            )
        _validate_lineage(connection)
        _check_spool_bound(connection)

        current_admissions = current_admission_writer.finish()
        current_normalized = current_normalized_writer.finish()
        censored_admissions = censored_admission_writer.finish()
        censored_normalized = censored_normalized_writer.finish()
        admission_descriptors = {
            SignalArm.CURRENT_VINTAGE: current_admissions,
            SignalArm.CONSERVATIVE_CENSORED: censored_admissions,
        }
        normalized_descriptors = {
            SignalArm.CURRENT_VINTAGE: current_normalized,
            SignalArm.CONSERVATIVE_CENSORED: censored_normalized,
        }

        evidence_items = lambda: _iter_jsonl_fragments_at(
            stage_fd,
            evidence_descriptor.relative_path,
            evidence_descriptor,
        )
        source_projection_sha256 = _source_projection(source_bindings)
        row_projection_sha256 = _row_projection_at(stage_fd, evidence_descriptor)
        _authority_byte_count, evidence_authority_sha256 = _digest_chunks(
            _iter_canonical_object(
                _authority_fields(
                    pair_id=pair_id,
                    pair_sha256=pair_sha256,
                    sources=source_bindings,
                    evidence_items=evidence_items,
                ),
                terminate=True,
            )
        )
        evidence_authority_id = (
            f"arv2-production-evidence-{evidence_authority_sha256[:24]}"
        )

        package_fields = _package_fields(
            pair_id=pair_id,
            pair_sha256=pair_sha256,
            sources=source_bindings,
            evidence_items=evidence_items,
            evidence_row_count=evidence_count,
            component_counts=component_counts,
            source_projection_sha256=source_projection_sha256,
            row_projection_sha256=row_projection_sha256,
        )
        package_byte_count, package_sha256 = _write_private_chunks_at(
            stage_fd,
            EVIDENCE_PACKAGE,
            _iter_canonical_object(package_fields, terminate=True),
            created_files=created_files,
        )
        package_descriptor = _descriptor_for_document(
            kind="evidence_package",
            path=Path(EVIDENCE_PACKAGE),
            byte_count=package_byte_count,
            sha256=package_sha256,
        )

        report_fields = _report_semantic_fields(
            connection, pair_id=pair_id, pair_sha256=pair_sha256
        )
        _semantic_report_bytes, report_sha256 = _digest_chunks(
            _iter_canonical_object(report_fields, terminate=True)
        )
        full_report_fields = {
            **report_fields,
            "report_sha256": report_sha256,
        }
        report_byte_count, report_file_sha256 = _write_private_chunks_at(
            stage_fd,
            COMPARISON_REPORT,
            _iter_canonical_object(full_report_fields, terminate=True),
            created_files=created_files,
        )
        report_descriptor = _descriptor_for_document(
            kind="comparison_report",
            path=Path(COMPARISON_REPORT),
            byte_count=report_byte_count,
            sha256=report_file_sha256,
        )

        batch_values: list[PhysicalProductionInputBatchArchive] = []
        for arm in _ARM_ORDER:
            admission_descriptor = admission_descriptors[arm]
            normalized_descriptor = normalized_descriptors[arm]
            fields = _batch_fields(
                evidence_authority_id=evidence_authority_id,
                evidence_authority_sha256=evidence_authority_sha256,
                pair_id=pair_id,
                pair_sha256=pair_sha256,
                arm=arm,
                total_source_row_count=source_count,
                source_view_included_count=included_counts[arm],
                directional_candidate_count=directional_counts[arm],
                normalized_row_count=normalized_counts[arm],
                admission_items=lambda item=admission_descriptor: (
                    _iter_jsonl_fragments_at(
                        stage_fd, item.relative_path, item
                    )
                ),
                normalized_items=lambda item=normalized_descriptor: (
                    _iter_jsonl_fragments_at(
                        stage_fd, item.relative_path, item
                    )
                ),
                comparison_report_chunks=lambda: _iter_file_fragment_at(
                    stage_fd,
                    report_descriptor.relative_path,
                    expected_bytes=report_descriptor.byte_count,
                    expected_sha256=report_descriptor.sha256,
                ),
            )
            _batch_byte_count, batch_sha256 = _digest_chunks(
                _iter_canonical_object(fields, terminate=True)
            )
            batch_values.append(
                PhysicalProductionInputBatchArchive(
                    signal_arm=arm,
                    batch_id=f"arv2-preoutcome-batch-{batch_sha256[:24]}",
                    batch_sha256=batch_sha256,
                    source_view=_ARM_TO_VIEW[arm],
                    source_view_label=_ARM_TO_LABEL[arm],
                    total_source_row_count=source_count,
                    source_view_included_count=included_counts[arm],
                    directional_candidate_count=directional_counts[arm],
                    normalized_row_count=normalized_counts[arm],
                    refused_directional_count=(
                        directional_counts[arm] - normalized_counts[arm]
                    ),
                    admissions=admission_descriptor,
                    normalized_rows=normalized_descriptor,
                )
            )
        batches = tuple(batch_values)

        _validate_source_bindings(source_bindings)
        if canonical_json_bytes(
            [_PINNED_SOURCE_BINDING_TO_RECORD(item) for item in source_bindings]
        ) != source_binding_bytes:
            raise PhysicalProductionInputArchiveError(
                "source bindings changed during physical C2 construction"
            )

        manifest_semantic = _manifest_semantic_record(
            parent_archive_id=parent_archive_id,
            parent_archive_sha256=parent_archive_sha256,
            fixture_only=fixture_only,
            pair_id=pair_id,
            pair_sha256=pair_sha256,
            evidence_authority_id=evidence_authority_id,
            evidence_authority_sha256=evidence_authority_sha256,
            source_bindings=source_bindings,
            source_projection_sha256=source_projection_sha256,
            row_projection_sha256=row_projection_sha256,
            evidence_row_count=evidence_count,
            component_present_counts=component_counts,
            evidence_rows=evidence_descriptor,
            evidence_package=package_descriptor,
            comparison_report=report_descriptor,
            comparison_report_sha256=report_sha256,
            batches=batches,
        )
        archive_sha256 = sha256_bytes(canonical_json_bytes(manifest_semantic))
        archive_id = f"arv2-physical-c2-{archive_sha256[:24]}"
        manifest_bytes = canonical_json_bytes(
            {
                **manifest_semantic,
                "archive_id": archive_id,
                "archive_sha256": archive_sha256,
            }
        )
        _write_private_chunks_at(
            stage_fd,
            ARCHIVE_MANIFEST,
            (manifest_bytes,),
            created_files=created_files,
        )
        _write_private_chunks_at(
            stage_fd,
            ARCHIVE_MANIFEST_DIGEST,
            ((sha256_bytes(manifest_bytes) + "\n").encode("ascii"),),
            created_files=created_files,
        )
        connection.close()
        connection = None
        spool_identity = created_files["spool.sqlite3"]
        try:
            quarantine_name, held_spool_fd = _quarantine_created_file_at(
                stage_fd,
                "spool.sqlite3",
                spool_identity,
                "physical C2 SQLite spool",
            )
            try:
                _unlink_quarantined_file_at(
                    stage_fd,
                    quarantine_name,
                    held_spool_fd,
                    spool_identity,
                    "physical C2 SQLite spool",
                )
            finally:
                os.close(held_spool_fd)
        except (OSError, PhysicalProductionInputArchiveError):
            preserve_staging = True
            raise
        del created_files["spool.sqlite3"]
        _fsync_fd(stage_fd, "physical C2 staging archive")
        require_build_directories_live()
        try:
            stage_inventory = set(os.listdir(stage_fd))
        except OSError as exc:
            raise PhysicalProductionInputArchiveError(
                "physical C2 staging inventory is unavailable"
            ) from exc
        if stage_inventory != set(created_files):
            raise PhysicalProductionInputArchiveError(
                "physical C2 staging inventory changed before publication"
            )
        for filename, file_identity in created_files.items():
            _require_created_file_identity_at(
                stage_fd,
                filename,
                file_identity,
                "physical C2 staging member",
            )
        final = root / archive_id
        if _entry_exists_at(root_fd, archive_id):
            raise PhysicalProductionInputArchiveError(
                "content-addressed physical C2 archive already exists"
            )
        _require_static_contract()
        require_build_directories_live()
        _fsync_fd(stage_fd, "physical C2 staging archive")
        _rename_at(root_fd, stage_name, archive_id)
        published = True
        try:
            _require_pinned_child_identity(
                root_fd,
                archive_id,
                stage_fd,
                "published physical C2 archive",
            )
        except PhysicalProductionInputArchiveError as exc:
            raise PhysicalProductionInputArchiveError(
                "physical C2 publication state is ambiguous after identity verification failure"
            ) from exc
        try:
            _fsync_fd(root_fd, "physical C2 root publication")
        except PhysicalProductionInputArchiveError as sync_error:
            try:
                _rollback_published_archive(
                    root_path=root,
                    root_fd=root_fd,
                    final_name=archive_id,
                    stage_name=stage_name,
                    stage_fd=stage_fd,
                )
            except PhysicalProductionInputArchiveError:
                preserve_staging = True
                publication_ambiguous = True
                raise
            published = False
            raise sync_error
        value = object.__new__(PhysicalProductionInputArchive)
        values: dict[str, object] = {
            "schema": ARCHIVE_SCHEMA,
            "archive_id": archive_id,
            "archive_sha256": archive_sha256,
            "archive_path": final,
            "accepted_risk_archive": accepted_risk_archive,
            "parent_archive_id": parent_archive_id,
            "parent_archive_sha256": parent_archive_sha256,
            "fixture_only": fixture_only,
            "pair_id": pair_id,
            "pair_sha256": pair_sha256,
            "evidence_authority_id": evidence_authority_id,
            "evidence_authority_sha256": evidence_authority_sha256,
            "source_bindings": source_bindings,
            "source_projection_sha256": source_projection_sha256,
            "row_projection_sha256": row_projection_sha256,
            "evidence_row_count": evidence_count,
            "component_present_counts": component_counts,
            "evidence_rows": evidence_descriptor,
            "evidence_package": package_descriptor,
            "comparison_report": report_descriptor,
            "comparison_report_sha256": report_sha256,
            "batches": batches,
            "maximum_source_row_count": MAX_SOURCE_ROWS,
            "maximum_evidence_row_count": MAX_EVIDENCE_ROWS,
            "full_pair_materialized": False,
            "full_evidence_materialized": False,
            "full_admission_census_materialized": False,
            "provider_access": False,
            "credential_access": False,
            "quantconnect_access": False,
            "outcome_access": False,
            "result_access": False,
            "deployment": False,
            "orders": False,
            "trading": False,
        }
        if set(values) != {field.name for field in dataclasses.fields(value)}:
            raise PhysicalProductionInputArchiveError(
                "physical C2 archive field inventory changed"
            )
        for name, item in values.items():
            object.__setattr__(value, name, item)
        identity = id(value)
        registered_identity = identity
        reference = weakref.ref(value, lambda ref, key=identity: _forget(key, ref))
        with _AUTHORITY_LOCK:
            _AUTHORITIES[identity] = (
                reference,
                _archive_fingerprint(value),
                _archive_topology(value),
                os.getpid(),
                _directory_identity(os.fstat(stage_fd)),
            )
        _require_static_contract()
        return require_physical_production_input_archive(value)
    except BaseException as primary_error:
        if published and not publication_ambiguous:
            try:
                _rollback_published_archive(
                    root_path=root,
                    root_fd=root_fd,
                    final_name=archive_id,
                    stage_name=stage_name,
                    stage_fd=stage_fd,
                )
            except PhysicalProductionInputArchiveError as rollback_error:
                preserve_staging = True
                if registered_identity is not None:
                    with _AUTHORITY_LOCK:
                        _AUTHORITIES.pop(registered_identity, None)
                raise rollback_error from primary_error
            published = False
        if registered_identity is not None:
            with _AUTHORITY_LOCK:
                _AUTHORITIES.pop(registered_identity, None)
        if _is_sqlite_full(primary_error):
            raise PhysicalProductionInputCapacityError(
                "C2 SQLite spool reached its fixed hard page bound"
            ) from primary_error
        raise
    finally:
        if connection is not None:
            connection.close()
        for writer in writers:
            if not writer._closed:
                writer.abort()
        if not published and not preserve_staging:
            _safe_cleanup_stage_at(
                root_path=root,
                root_fd=root_fd,
                stage_name=stage_name,
                stage_fd=stage_fd,
                created_files=created_files,
            )
        os.close(stage_fd)
        os.close(root_fd)


def build_physical_production_input_archive(
    accepted_risk_archive: object,
    *,
    source_bindings: tuple[EvidenceSourceBinding, ...],
    row_evidence: Iterable[ProductionRowEvidence],
    output_root: Path,
) -> PhysicalProductionInputArchive:
    """Derive physical C2 from authenticated disk-backed C1, without outcomes."""

    _require_static_contract()
    return _build_from_physical_c1(
        accepted_risk_archive,
        source_bindings=source_bindings,
        row_evidence=row_evidence,
        output_root=output_root,
        fixture_only=False,
    )


def _build_test_fixture_physical_production_input_archive_from_physical_c1(
    accepted_risk_archive: object,
    *,
    source_bindings: tuple[EvidenceSourceBinding, ...],
    row_evidence: Iterable[ProductionRowEvidence],
    output_root: Path,
) -> PhysicalProductionInputArchive:
    """Test-only physical-C1 integration seam; its result stays a fixture."""

    return _build_from_physical_c1(
        accepted_risk_archive,
        source_bindings=source_bindings,
        row_evidence=row_evidence,
        output_root=output_root,
        fixture_only=True,
    )


def _build_from_physical_c1(
    accepted_risk_archive: object,
    *,
    source_bindings: tuple[EvidenceSourceBinding, ...],
    row_evidence: Iterable[ProductionRowEvidence],
    output_root: Path,
    fixture_only: bool,
) -> PhysicalProductionInputArchive:
    _require_static_contract()

    if (
        type(accepted_risk_archive) is not _PINNED_C1_ARCHIVE_TYPE
    ):
        raise PhysicalProductionInputArchiveError(
            "production physical C2 requires the exact physical C1 authority"
        )
    try:
        c1 = _PINNED_REQUIRE_C1_ARCHIVE(accepted_risk_archive)
    except ValueError as exc:
        raise PhysicalProductionInputArchiveError(
            "physical C1 authority could not be reauthenticated"
        ) from exc
    if not isinstance(output_root, Path):
        raise PhysicalProductionInputArchiveError("archive_root must be a Path")
    output = output_root.absolute()
    for immutable_input in (c1.source_artifact_path, c1.archive_path):
        try:
            output.relative_to(immutable_input.absolute())
        except ValueError:
            continue
        raise PhysicalProductionInputArchiveError(
            "physical C2 output overlaps an immutable C1 input"
        )
    if type(c1.capture_transport) is not str:
        raise PhysicalProductionInputArchiveError(
            "physical C1 capture transport changed type"
        )
    if fixture_only:
        if c1.capture_transport == _PINNED_PRODUCTION_C1_TRANSPORT:
            raise PhysicalProductionInputArchiveError(
                "test fixture seam refuses a production C1 archive"
            )
    else:
        if c1.capture_transport != _PINNED_PRODUCTION_C1_TRANSPORT:
            raise PhysicalProductionInputArchiveError(
                "production physical C2 requires production C1 transport"
            )
        try:
            within = os.path.commonpath(
                (str(output), str(_PINNED_REPOSITORY_ARTIFACTS_ROOT.absolute()))
            ) == str(_PINNED_REPOSITORY_ARTIFACTS_ROOT.absolute())
        except ValueError:
            within = False
        if not within:
            raise PhysicalProductionInputArchiveError(
                "production physical C2 output must remain under artifacts"
            )
    return _build_physical_archive(
        accepted_risk_archive=c1,
        parent_archive_id=c1.archive_id,
        parent_archive_sha256=c1.archive_sha256,
        fixture_only=fixture_only,
        pair_id=c1.pair_id,
        pair_sha256=c1.pair_sha256,
        expected_source_row_count=c1.source_row_count,
        expected_current_included_count=c1.current_included_count,
        expected_censored_included_count=c1.censored_included_count,
        source_rows=lambda: _PINNED_ITER_C1_ROWS(c1),
        source_bindings=source_bindings,
        row_evidence=row_evidence,
        archive_root=output,
    )


def build_test_fixture_physical_production_input_archive(
    authority: ProductionEvidenceAuthority,
    *,
    output_root: Path,
) -> PhysicalProductionInputArchive:
    """Test-only legacy oracle seam; its result is never formal-run eligible."""

    _require_static_contract()
    if type(authority) is not ProductionEvidenceAuthority:
        raise PhysicalProductionInputArchiveError(
            "test fixture requires an exact legacy C2 authority"
        )
    try:
        _c2.require_production_evidence_authority(authority)
    except ValueError as exc:
        raise PhysicalProductionInputArchiveError(
            "legacy C2 test authority is not authenticated"
        ) from exc
    pair = authority.pair
    return _build_physical_archive(
        accepted_risk_archive=None,
        parent_archive_id=pair.pair_id,
        parent_archive_sha256=pair.pair_sha256,
        fixture_only=True,
        pair_id=pair.pair_id,
        pair_sha256=pair.pair_sha256,
        expected_source_row_count=len(pair.rows),
        expected_current_included_count=sum(
            row.current_view.included for row in pair.rows
        ),
        expected_censored_included_count=sum(
            row.censored_view.included for row in pair.rows
        ),
        source_rows=lambda: iter(pair.rows),
        source_bindings=authority.source_bindings,
        row_evidence=iter(authority.row_evidence),
        archive_root=output_root,
    )


def _manifest_from_value(value: PhysicalProductionInputArchive) -> dict[str, object]:
    return _manifest_semantic_record(
        parent_archive_id=value.parent_archive_id,
        parent_archive_sha256=value.parent_archive_sha256,
        fixture_only=value.fixture_only,
        pair_id=value.pair_id,
        pair_sha256=value.pair_sha256,
        evidence_authority_id=value.evidence_authority_id,
        evidence_authority_sha256=value.evidence_authority_sha256,
        source_bindings=value.source_bindings,
        source_projection_sha256=value.source_projection_sha256,
        row_projection_sha256=value.row_projection_sha256,
        evidence_row_count=value.evidence_row_count,
        component_present_counts=value.component_present_counts,
        evidence_rows=value.evidence_rows,
        evidence_package=value.evidence_package,
        comparison_report=value.comparison_report,
        comparison_report_sha256=value.comparison_report_sha256,
        batches=value.batches,
    )


def _validate_batch_surface(value: PhysicalProductionInputBatchArchive) -> None:
    if type(value) is not PhysicalProductionInputBatchArchive:
        raise PhysicalProductionInputArchiveError(
            "physical batch requires the exact archive type"
        )
    if value.signal_arm not in _ARM_ORDER or type(value.signal_arm) is not SignalArm:
        raise PhysicalProductionInputArchiveError("physical batch arm changed")
    if (
        type(value.source_view) is not InputView
        or value.source_view is not _ARM_TO_VIEW[value.signal_arm]
        or type(value.source_view_label) is not str
        or value.source_view_label != _ARM_TO_LABEL[value.signal_arm]
    ):
        raise PhysicalProductionInputArchiveError(
            "physical batch view identity changed"
        )
    try:
        require_identifier(value.batch_id, "physical batch_id")
        require_sha256(value.batch_sha256, "physical batch_sha256")
        for name in (
            "total_source_row_count",
            "source_view_included_count",
            "directional_candidate_count",
            "normalized_row_count",
            "refused_directional_count",
        ):
            require_int(getattr(value, name), f"physical batch {name}", minimum=0)
    except ValueError as exc:
        raise PhysicalProductionInputArchiveError(
            "physical batch scalar changed"
        ) from exc
    if (
        value.batch_id != f"arv2-preoutcome-batch-{value.batch_sha256[:24]}"
        or value.refused_directional_count
        != value.directional_candidate_count - value.normalized_row_count
        or value.admissions.row_count != value.total_source_row_count
        or value.normalized_rows.row_count != value.normalized_row_count
    ):
        raise PhysicalProductionInputArchiveError(
            "physical batch census or identity changed"
        )
    if (
        type(value.admissions) is not PhysicalC2FileDescriptor
        or type(value.normalized_rows) is not PhysicalC2FileDescriptor
    ):
        raise PhysicalProductionInputArchiveError(
            "physical batch descriptors changed type"
        )
    value.admissions.__post_init__()
    value.normalized_rows.__post_init__()


def _validate_archive_surface(value: PhysicalProductionInputArchive) -> None:
    if type(value) is not PhysicalProductionInputArchive:
        raise PhysicalProductionInputArchiveError(
            "physical C2 archive requires the exact built type"
        )
    if not isinstance(value.archive_path, Path):
        raise PhysicalProductionInputArchiveError("physical C2 path changed type")
    if type(value.fixture_only) is not bool:
        raise PhysicalProductionInputArchiveError("fixture marker changed type")
    try:
        require_identifier(value.archive_id, "physical C2 archive_id")
        require_sha256(value.archive_sha256, "physical C2 archive_sha256")
        require_identifier(value.parent_archive_id, "physical C2 parent_archive_id")
        require_sha256(
            value.parent_archive_sha256, "physical C2 parent_archive_sha256"
        )
        require_identifier(value.pair_id, "physical C2 pair_id")
        require_sha256(value.pair_sha256, "physical C2 pair_sha256")
        require_identifier(
            value.evidence_authority_id, "physical C2 evidence_authority_id"
        )
        require_sha256(
            value.evidence_authority_sha256,
            "physical C2 evidence_authority_sha256",
        )
        require_sha256(
            value.source_projection_sha256,
            "physical C2 source_projection_sha256",
        )
        require_sha256(
            value.row_projection_sha256,
            "physical C2 row_projection_sha256",
        )
        require_sha256(
            value.comparison_report_sha256,
            "physical C2 comparison_report_sha256",
        )
        require_int(value.evidence_row_count, "physical evidence_row_count", minimum=0)
    except ValueError as exc:
        raise PhysicalProductionInputArchiveError(
            "physical C2 authority scalar changed"
        ) from exc
    _validate_source_bindings(value.source_bindings)
    if (
        type(value.component_present_counts) is not tuple
        or tuple(kind for kind, _count in value.component_present_counts)
        != _COMPONENT_NAMES
        or any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not int
            or item[1] < 0
            or item[1] > value.evidence_row_count
            for item in value.component_present_counts
        )
    ):
        raise PhysicalProductionInputArchiveError(
            "physical C2 component census changed"
        )
    if type(value.batches) is not tuple or tuple(
        item.signal_arm for item in value.batches
    ) != _ARM_ORDER:
        raise PhysicalProductionInputArchiveError(
            "physical C2 batch order changed"
        )
    for batch in value.batches:
        _validate_batch_surface(batch)
        if batch.total_source_row_count > value.maximum_source_row_count:
            raise PhysicalProductionInputCapacityError(
                "physical batch exceeds its source-row bound"
            )
    descriptors = (
        value.evidence_rows,
        value.evidence_package,
        value.comparison_report,
        *(
            descriptor
            for batch in value.batches
            for descriptor in (batch.admissions, batch.normalized_rows)
        ),
    )
    if any(type(item) is not PhysicalC2FileDescriptor for item in descriptors):
        raise PhysicalProductionInputArchiveError(
            "physical C2 file descriptor type changed"
        )
    for descriptor in descriptors:
        descriptor.__post_init__()
    if len({item.relative_path for item in descriptors}) != len(descriptors):
        raise PhysicalProductionInputArchiveError(
            "physical C2 file paths are not unique"
        )
    if (
        value.evidence_rows.row_count != value.evidence_row_count
        or value.maximum_source_row_count != MAX_SOURCE_ROWS
        or value.maximum_evidence_row_count != MAX_EVIDENCE_ROWS
        or value.evidence_row_count > value.maximum_evidence_row_count
    ):
        raise PhysicalProductionInputArchiveError(
            "physical C2 declared bounds or evidence census changed"
        )
    false_flags = (
        value.full_pair_materialized,
        value.full_evidence_materialized,
        value.full_admission_census_materialized,
        value.provider_access,
        value.credential_access,
        value.quantconnect_access,
        value.outcome_access,
        value.result_access,
        value.deployment,
        value.orders,
        value.trading,
    )
    if any(type(item) is not bool or item for item in false_flags):
        raise PhysicalProductionInputArchiveError(
            "physical C2 archive acquired a forbidden flag"
        )
    if value.fixture_only:
        if value.accepted_risk_archive is not None and (
            type(value.accepted_risk_archive) is not _PINNED_C1_ARCHIVE_TYPE
        ):
            raise PhysicalProductionInputArchiveError(
                "test fixture retained an invalid physical C1 parent"
            )
    else:
        if type(value.accepted_risk_archive) is not _PINNED_C1_ARCHIVE_TYPE:
            raise PhysicalProductionInputArchiveError(
                "production physical C2 lost its exact C1 parent"
            )


def require_physical_production_input_archive(
    value: PhysicalProductionInputArchive,
) -> PhysicalProductionInputArchive:
    """Reauthenticate builder identity, manifest, inventory, and every byte."""

    _require_static_contract()
    _validate_archive_surface(value)
    with _AUTHORITY_LOCK:
        registered = _AUTHORITIES.get(id(value))
    if (
        registered is None
        or registered[0]() is not value
        or registered[3] != os.getpid()
        or registered[1] != _archive_fingerprint(value)
        or registered[2] != _archive_topology(value)
    ):
        raise PhysicalProductionInputArchiveError(
            "physical C2 archive is not current builder authority"
        )
    if value.accepted_risk_archive is not None:
        try:
            c1 = _PINNED_REQUIRE_C1_ARCHIVE(value.accepted_risk_archive)
        except (TypeError, ValueError) as exc:
            raise PhysicalProductionInputArchiveError(
                "physical C2 parent C1 no longer authenticates"
            ) from exc
        if (
            c1.archive_id != value.parent_archive_id
            or c1.archive_sha256 != value.parent_archive_sha256
            or c1.pair_id != value.pair_id
            or c1.pair_sha256 != value.pair_sha256
        ):
            raise PhysicalProductionInputArchiveError(
                "physical C2 parent lineage changed"
            )
    semantic = _manifest_from_value(value)
    digest = sha256_bytes(canonical_json_bytes(semantic))
    if (
        value.schema != ARCHIVE_SCHEMA
        or value.archive_sha256 != digest
        or value.archive_id != f"arv2-physical-c2-{digest[:24]}"
    ):
        raise PhysicalProductionInputArchiveError(
            "physical C2 content identity changed"
        )
    descriptors = (
        value.evidence_rows,
        value.evidence_package,
        value.comparison_report,
        *(
            descriptor
            for batch in value.batches
            for descriptor in (batch.admissions, batch.normalized_rows)
        ),
    )
    expected_names = {
        ARCHIVE_MANIFEST,
        ARCHIVE_MANIFEST_DIGEST,
        *(item.relative_path for item in descriptors),
    }
    expected_manifest = canonical_json_bytes(
        {
            **semantic,
            "archive_id": value.archive_id,
            "archive_sha256": value.archive_sha256,
        }
    )
    archive_path, archive_fd = _open_directory_path(
        value.archive_path, name="physical C2 archive"
    )
    try:
        before = os.fstat(archive_fd)
        if _directory_identity(before) != registered[4]:
            raise PhysicalProductionInputArchiveError(
                "physical C2 archive path no longer names builder authority"
            )
        try:
            observed_names = set(os.listdir(archive_fd))
        except OSError as exc:
            raise PhysicalProductionInputArchiveError(
                "physical C2 archive inventory is unavailable"
            ) from exc
        if observed_names != expected_names:
            raise PhysicalProductionInputArchiveError(
                "physical C2 archive inventory changed"
            )
        visited: dict[str, tuple[int, int, int, int, int]] = {}
        manifest, visited[ARCHIVE_MANIFEST] = _read_private_file_at(
            archive_fd,
            ARCHIVE_MANIFEST,
            maximum_bytes=MAX_MANIFEST_BYTES,
            name="physical C2 manifest",
        )
        manifest_digest, visited[ARCHIVE_MANIFEST_DIGEST] = (
            _read_private_file_at(
                archive_fd,
                ARCHIVE_MANIFEST_DIGEST,
                maximum_bytes=65,
                name="physical C2 manifest digest",
            )
        )
        if (
            manifest != expected_manifest
            or manifest_digest
            != (sha256_bytes(manifest) + "\n").encode("ascii")
        ):
            raise PhysicalProductionInputArchiveError(
                "physical C2 manifest does not authenticate"
            )
        live_directory = (archive_path, archive_fd, "physical C2 archive")
        for descriptor in descriptors:
            for _chunk in _iter_private_file_at(
                archive_fd,
                descriptor.relative_path,
                expected_bytes=descriptor.byte_count,
                expected_sha256=descriptor.sha256,
                name=descriptor.relative_path,
                identity_sink=visited,
                live_directory=live_directory,
            ):
                pass
        for filename, file_identity in visited.items():
            _require_visited_file_identity_at(
                archive_fd,
                filename,
                file_identity,
                filename,
            )
        after = os.fstat(archive_fd)
        try:
            final_names = set(os.listdir(archive_fd))
        except OSError as exc:
            raise PhysicalProductionInputArchiveError(
                "physical C2 archive inventory changed during traversal"
            ) from exc
        if (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_uid,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise PhysicalProductionInputArchiveError(
                "physical C2 archive directory changed during traversal"
            )
        if final_names != expected_names:
            raise PhysicalProductionInputArchiveError(
                "physical C2 archive inventory changed during traversal"
            )
        _require_reopened_directory_identity(
            archive_path, archive_fd, "physical C2 archive"
        )
        _require_static_contract()
    finally:
        os.close(archive_fd)
    return value


def physical_production_batch(
    value: PhysicalProductionInputArchive,
    signal_arm: SignalArm,
) -> PhysicalProductionInputBatchArchive:
    archive = require_physical_production_input_archive(value)
    if type(signal_arm) is not SignalArm:
        raise PhysicalProductionInputArchiveError("signal_arm must have exact type")
    return archive.batches[_ARM_ORDER.index(signal_arm)]


def iter_physical_production_row_evidence(
    value: PhysicalProductionInputArchive,
) -> Iterator[ProductionRowEvidence]:
    archive = require_physical_production_input_archive(value)
    yield from _iter_evidence_rows(archive)


def _open_bound_archive_directory(
    archive: PhysicalProductionInputArchive,
) -> tuple[Path, int]:
    with _AUTHORITY_LOCK:
        registered = _AUTHORITIES.get(id(archive))
    if (
        registered is None
        or registered[0]() is not archive
        or registered[3] != os.getpid()
    ):
        raise PhysicalProductionInputArchiveError(
            "physical C2 archive is not current builder authority"
        )
    archive_path, archive_fd = _open_directory_path(
        archive.archive_path, name="physical C2 archive"
    )
    if _directory_identity(os.fstat(archive_fd)) != registered[4]:
        os.close(archive_fd)
        raise PhysicalProductionInputArchiveError(
            "physical C2 archive path no longer names builder authority"
        )
    return archive_path, archive_fd


def _iter_evidence_rows(
    archive: PhysicalProductionInputArchive,
) -> Iterator[ProductionRowEvidence]:
    archive_path, archive_fd = _open_bound_archive_directory(archive)
    visited: dict[str, tuple[int, int, int, int, int]] = {}
    try:
        previous: tuple[int, int, int] | None = None
        for payload in _iter_jsonl_fragments_at(
            archive_fd,
            archive.evidence_rows.relative_path,
            archive.evidence_rows,
            identity_sink=visited,
            live_directory=(archive_path, archive_fd, "physical C2 archive"),
        ):
            row = _decode_evidence_record(
                _strict_record(payload, "physical evidence row")
            )
            key = row.locator.sort_key
            if previous is not None and key <= previous:
                raise PhysicalProductionInputArchiveError(
                    "physical evidence row order changed"
                )
            previous = key
            yield row
        for filename, file_identity in visited.items():
            _require_visited_file_identity_at(
                archive_fd, filename, file_identity, filename
            )
        _require_reopened_directory_identity(
            archive_path, archive_fd, "physical C2 archive"
        )
        _require_static_contract()
    finally:
        os.close(archive_fd)


def iter_physical_production_normalized_rows(
    value: PhysicalProductionInputArchive,
    signal_arm: SignalArm,
) -> Iterator[NormalizedPreOutcomeRow]:
    archive = require_physical_production_input_archive(value)
    if type(signal_arm) is not SignalArm:
        raise PhysicalProductionInputArchiveError("signal_arm must have exact type")
    batch = archive.batches[_ARM_ORDER.index(signal_arm)]
    yield from _iter_normalized_rows(archive, batch)


def _iter_normalized_rows(
    archive: PhysicalProductionInputArchive,
    batch: PhysicalProductionInputBatchArchive,
) -> Iterator[NormalizedPreOutcomeRow]:
    archive_path, archive_fd = _open_bound_archive_directory(archive)
    visited: dict[str, tuple[int, int, int, int, int]] = {}
    try:
        previous: tuple[int, int, int] | None = None
        for payload in _iter_jsonl_fragments_at(
            archive_fd,
            batch.normalized_rows.relative_path,
            batch.normalized_rows,
            identity_sink=visited,
            live_directory=(archive_path, archive_fd, "physical C2 archive"),
        ):
            row = _decode_normalized_record(
                _strict_record(payload, "physical normalized row")
            )
            key = row.source_locator.sort_key
            if row.signal_arm is not batch.signal_arm:
                raise PhysicalProductionInputArchiveError(
                    "physical normalized row arm changed"
                )
            if previous is not None and key <= previous:
                raise PhysicalProductionInputArchiveError(
                    "physical normalized row order changed"
                )
            previous = key
            yield row
        for filename, file_identity in visited.items():
            _require_visited_file_identity_at(
                archive_fd, filename, file_identity, filename
            )
        _require_reopened_directory_identity(
            archive_path, archive_fd, "physical C2 archive"
        )
        _require_static_contract()
    finally:
        os.close(archive_fd)


def iter_physical_normalized_evidence_rows(
    value: PhysicalProductionInputArchive,
    signal_arm: SignalArm,
) -> Iterator[PhysicalNormalizedEvidenceRow]:
    """Merge-join normalized rows to evidence with O(1) retained row state."""

    archive = require_physical_production_input_archive(value)
    if type(signal_arm) is not SignalArm:
        raise PhysicalProductionInputArchiveError("signal_arm must have exact type")
    batch = archive.batches[_ARM_ORDER.index(signal_arm)]
    evidence_iterator = _iter_evidence_rows(archive)
    evidence = next(evidence_iterator, None)
    for normalized in _iter_normalized_rows(archive, batch):
        target = normalized.source_locator.sort_key
        while evidence is not None and evidence.locator.sort_key < target:
            evidence = next(evidence_iterator, None)
        if evidence is None or evidence.locator != normalized.source_locator:
            raise PhysicalProductionInputArchiveError(
                "normalized row lost its exact physical evidence member"
            )
        yield PhysicalNormalizedEvidenceRow(
            normalized_row=normalized,
            evidence=evidence,
        )
        evidence = next(evidence_iterator, None)
    for _unused_evidence in evidence_iterator:
        pass


def require_reviewable_physical_production_archive(
    value: PhysicalProductionInputArchive,
) -> PhysicalProductionInputArchive:
    """Reject fixtures before a separate signed-review binding is attempted."""

    archive = require_physical_production_input_archive(value)
    if archive.fixture_only:
        raise PhysicalProductionInputArchiveError(
            "legacy fixture archive cannot be submitted for production review"
        )
    return archive


def _build_physical_formal_accepted_risk_pair_binding(
    accepted_risk_archive: object,
    production_input_archive: PhysicalProductionInputArchive,
    *,
    permit_fixture: bool,
) -> AcceptedRiskPairBinding:
    _require_static_contract()
    if (
        type(accepted_risk_archive) is not _PINNED_C1_ARCHIVE_TYPE
    ):
        raise PhysicalProductionInputArchiveError(
            "formal pair binding requires exact physical C1 authority"
        )
    try:
        c1 = _PINNED_REQUIRE_C1_ARCHIVE(accepted_risk_archive)
        c2 = require_physical_production_input_archive(production_input_archive)
    except (AttributeError, TypeError, ValueError) as exc:
        raise PhysicalProductionInputArchiveError(
            "physical C1/C2 pair could not be reauthenticated"
        ) from exc
    if c2.fixture_only and not permit_fixture:
        raise PhysicalProductionInputArchiveError(
            "fixture physical C2 cannot produce a production formal pair binding"
        )
    if (
        c2.accepted_risk_archive is not c1
        or c2.parent_archive_id != c1.archive_id
        or c2.parent_archive_sha256 != c1.archive_sha256
        or c2.pair_id != c1.pair_id
        or c2.pair_sha256 != c1.pair_sha256
    ):
        raise PhysicalProductionInputArchiveError(
            "physical C1 and C2 do not share exact parent identity"
        )
    current, censored = c2.batches
    if (
        current.signal_arm is not SignalArm.CURRENT_VINTAGE
        or censored.signal_arm is not SignalArm.CONSERVATIVE_CENSORED
        or current.total_source_row_count != c1.source_row_count
        or censored.total_source_row_count != c1.source_row_count
        or current.source_view_included_count != c1.current_included_count
        or censored.source_view_included_count != c1.censored_included_count
    ):
        raise PhysicalProductionInputArchiveError(
            "physical C2 batches do not census the exact C1 source views"
        )
    guidance_admitted_count = 0
    pre_2013_admitted_count = 0
    observed_normalized = {arm: 0 for arm in _ARM_ORDER}
    for batch in c2.batches:
        for row in _iter_normalized_rows(c2, batch):
            observed_normalized[batch.signal_arm] += 1
            guidance_admitted_count += int(
                row.source_role is MassiveSourceRole.CORPORATE_GUIDANCE
            )
            pre_2013_admitted_count += int(row.event_date[:4]) < 2013
    if any(
        observed_normalized[batch.signal_arm] != batch.normalized_row_count
        for batch in c2.batches
    ):
        raise PhysicalProductionInputArchiveError(
            "physical C2 normalized-row census changed during formal binding"
        )
    try:
        binding = _PINNED_ACCEPTED_RISK_BINDING_TYPE(
            pair=c1.pair_artifact,
            capture_id=c1.capture_id,
            capture_sha256=c1.capture_sha256,
            current_source_included_count=current.source_view_included_count,
            censored_source_included_count=censored.source_view_included_count,
            current_admitted_decision_count=current.normalized_row_count,
            current_named_preoutcome_refusal_count=(
                current.source_view_included_count - current.normalized_row_count
            ),
            censored_admitted_decision_count=censored.normalized_row_count,
            censored_named_preoutcome_refusal_count=(
                censored.source_view_included_count - censored.normalized_row_count
            ),
            guidance_admitted_count=guidance_admitted_count,
            pre_2013_admitted_count=pre_2013_admitted_count,
            pristine_point_in_time=False,
            views_share_one_capture=True,
        )
        return _PINNED_REQUIRE_ACCEPTED_RISK_BINDING(binding)
    except (FormalRunProtocolError, AttributeError, TypeError, ValueError) as exc:
        raise PhysicalProductionInputArchiveError(
            "formal accepted-risk binding refused physical C1/C2 state"
        ) from exc


def build_physical_formal_accepted_risk_pair_binding(
    accepted_risk_archive: object,
    production_input_archive: PhysicalProductionInputArchive,
) -> AcceptedRiskPairBinding:
    """Bind production physical C1/C2; this does not grant formal readiness."""

    _require_static_contract()
    return _build_physical_formal_accepted_risk_pair_binding(
        accepted_risk_archive,
        production_input_archive,
        permit_fixture=False,
    )


def _build_test_fixture_physical_formal_accepted_risk_pair_binding(
    accepted_risk_archive: object,
    production_input_archive: PhysicalProductionInputArchive,
) -> AcceptedRiskPairBinding:
    """Offline oracle seam; public production binding always refuses fixtures."""

    return _build_physical_formal_accepted_risk_pair_binding(
        accepted_risk_archive,
        production_input_archive,
        permit_fixture=True,
    )


__all__ = [
    "ARCHIVE_SCHEMA",
    "PhysicalC2FileDescriptor",
    "PhysicalNormalizedEvidenceRow",
    "PhysicalProductionInputArchive",
    "PhysicalProductionInputArchiveError",
    "PhysicalProductionInputBatchArchive",
    "PhysicalProductionInputCapacityError",
    "build_physical_production_input_archive",
    "build_physical_formal_accepted_risk_pair_binding",
    "iter_physical_normalized_evidence_rows",
    "iter_physical_production_normalized_rows",
    "iter_physical_production_row_evidence",
    "physical_production_batch",
    "require_physical_production_input_archive",
    "require_reviewable_physical_production_archive",
]
