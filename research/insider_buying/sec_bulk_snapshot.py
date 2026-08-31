"""Offline integrity boundary for one SEC insider quarterly ZIP package.

This module accepts caller-supplied bytes only.  It performs no discovery or
network access and does not parse transaction rows, construct signals, load
outcomes, or interact with QuantConnect. Its single job is to integrity-check an
allowed quarterly archive named by the governing PDF and publish the exact
ZIP as a lineage-addressed, immutable raw snapshot.

Publication requires a caller-controlled output root with no untrusted actor
concurrently replacing path components. Cooperative writers are serialized,
and pre-existing redirects are refused, but this boundary does not claim
adversarial filesystem-race resistance.
"""
from __future__ import annotations

import codecs
import hashlib
import io
import json
import os
import re
import stat
import zipfile
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from data.hashing import canonical_json, hash_bytes, hash_payload
from ml.immutable_io import (
    ImmutableFileConflictError,
    exclusive_file_lock,
    publish_immutable_bytes,
)


SNAPSHOT_KIND = "sec-insider-bulk-quarter"
RAW_SNAPSHOT_CONTRACT_VERSION = 1
ALLOWED_SEC_TABLES = (
    "SUBMISSION.tsv",
    "REPORTINGOWNER.tsv",
    "NONDERIV_TRANS.tsv",
    "NONDERIV_HOLDING.tsv",
    "DERIV_TRANS.tsv",
    "DERIV_HOLDING.tsv",
    "FOOTNOTES.tsv",
    "OWNER_SIGNATURE.tsv",
)
REQUIRED_SEC_TABLES = (
    "SUBMISSION.tsv",
    "REPORTINGOWNER.tsv",
    "NONDERIV_TRANS.tsv",
)
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_MEMBER_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 4 * 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 250
MAX_MANIFEST_BYTES = 128 * 1024
MAX_COMMIT_BYTES = 16 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SEC_ZIP_URL_RE = re.compile(
    r"^https://(?:www\.)?sec\.gov/"
    r"(?P<prefix>(?:[A-Za-z0-9._~!$&'()*+,;=:@-]+/)*)"
    r"(?P<year>[0-9]{4})q(?P<quarter>[1-4])_form345\.zip$"
)
_SNAPSHOT_ID_RE = re.compile(
    r"^sec-insider-bulk-[0-9]{4}q[1-4]-[0-9a-f]{16}$"
)
_MANIFEST_NAME = "manifest.json"
_ARCHIVE_NAME = "archive.zip"
_COMMIT_NAME = "snapshot.commit.json"
_LOCK_SUFFIX = ".publication.lock"
_MANIFEST_KEYS = {
    "kind",
    "raw_contract_version",
    "year",
    "quarter",
    "source_url",
    "git_commit",
    "retrieved_at_utc",
    "archive_sha256",
    "archive_size_bytes",
    "members",
    "lineage_hash",
    "snapshot_id",
}
_MEMBER_KEYS = {
    "name",
    "sha256",
    "size_bytes",
    "compressed_size_bytes",
    "crc32",
    "compression",
}


class SecBulkSnapshotError(ValueError):
    """The raw SEC archive or immutable snapshot failed closed."""


class _SnapshotPublicationLock:
    """Translate only lock entry/exit failures into the domain contract."""

    def __init__(self, lock_path: Path) -> None:
        self._manager = exclusive_file_lock(lock_path)

    def __enter__(self):
        try:
            return self._manager.__enter__()
        except OSError as exc:
            raise SecBulkSnapshotError(
                "REFUSED: snapshot publication lock could not be acquired"
            ) from exc

    def __exit__(self, exc_type, exc, traceback):
        try:
            return self._manager.__exit__(exc_type, exc, traceback)
        except OSError as lock_exc:
            raise SecBulkSnapshotError(
                "REFUSED: snapshot publication lock could not be released"
            ) from lock_exc


@dataclass(frozen=True)
class SecBulkSource:
    """Caller-supplied provenance for one already-retrieved quarterly ZIP."""

    year: int
    quarter: int
    source_url: str
    git_commit: str
    retrieved_at: datetime
    _retrieved_at_utc: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.year) is not int or not 2006 <= self.year <= 9999:
            raise SecBulkSnapshotError("REFUSED: source year must be 2006 or later")
        if type(self.quarter) is not int or self.quarter not in {1, 2, 3, 4}:
            raise SecBulkSnapshotError("REFUSED: source quarter must be 1 through 4")
        if (
            not isinstance(self.source_url, str)
            or self.source_url != self.source_url.strip()
        ):
            raise SecBulkSnapshotError("REFUSED: source URL is not canonical")
        source_match = _SEC_ZIP_URL_RE.fullmatch(self.source_url)
        if source_match is None or any(
            segment in {".", ".."}
            for segment in source_match.group("prefix").split("/")
        ):
            raise SecBulkSnapshotError(
                "REFUSED: source URL must use HTTPS sec.gov and a canonical path"
            )
        if (
            int(source_match.group("year")) != self.year
            or int(source_match.group("quarter")) != self.quarter
        ):
            raise SecBulkSnapshotError(
                "REFUSED: source year and quarter must match the SEC ZIP filename"
            )
        if (
            not isinstance(self.git_commit, str)
            or _GIT_COMMIT_RE.fullmatch(self.git_commit) is None
        ):
            raise SecBulkSnapshotError(
                "REFUSED: source Git commit must be a full lowercase SHA-1"
            )
        if type(self.retrieved_at) is not datetime:
            raise SecBulkSnapshotError(
                "REFUSED: retrieval time must be a timezone-aware datetime"
            )
        try:
            offset = self.retrieved_at.utcoffset()
            retrieved_at_utc = self.retrieved_at.astimezone(timezone.utc).isoformat()
        except (OverflowError, TypeError, ValueError) as exc:
            raise SecBulkSnapshotError(
                "REFUSED: retrieval time cannot be represented in UTC"
            ) from exc
        if offset is None:
            raise SecBulkSnapshotError(
                "REFUSED: retrieval time must be timezone-aware"
            )
        object.__setattr__(self, "_retrieved_at_utc", retrieved_at_utc)

    @property
    def retrieved_at_utc(self) -> str:
        return self._retrieved_at_utc


@dataclass(frozen=True)
class SecBulkMember:
    name: str
    sha256: str
    size_bytes: int
    compressed_size_bytes: int
    crc32: str
    compression: str

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "compressed_size_bytes": self.compressed_size_bytes,
            "crc32": self.crc32,
            "compression": self.compression,
        }

    @classmethod
    def from_payload(cls, payload: object) -> "SecBulkMember":
        if not isinstance(payload, dict) or set(payload) != _MEMBER_KEYS:
            raise SecBulkSnapshotError("REFUSED: member manifest is malformed")
        name = payload.get("name")
        sha256 = payload.get("sha256")
        size_bytes = payload.get("size_bytes")
        compressed_size_bytes = payload.get("compressed_size_bytes")
        crc32 = payload.get("crc32")
        compression = payload.get("compression")
        if name not in ALLOWED_SEC_TABLES:
            raise SecBulkSnapshotError("REFUSED: member manifest has an unknown table")
        if not isinstance(sha256, str) or not _SHA256_RE.fullmatch(sha256):
            raise SecBulkSnapshotError("REFUSED: member manifest has an invalid hash")
        if (
            type(size_bytes) is not int
            or size_bytes < 0
            or type(compressed_size_bytes) is not int
            or compressed_size_bytes < 0
        ):
            raise SecBulkSnapshotError("REFUSED: member manifest has invalid sizes")
        if not isinstance(crc32, str) or re.fullmatch(r"[0-9a-f]{8}", crc32) is None:
            raise SecBulkSnapshotError("REFUSED: member manifest has an invalid CRC")
        if compression not in {"stored", "deflated"}:
            raise SecBulkSnapshotError(
                "REFUSED: member manifest has an unsupported compression"
            )
        return cls(
            name=name,
            sha256=sha256,
            size_bytes=size_bytes,
            compressed_size_bytes=compressed_size_bytes,
            crc32=crc32,
            compression=compression,
        )


@dataclass(frozen=True)
class SecBulkSnapshotIdentity:
    year: int
    quarter: int
    source_url: str
    git_commit: str
    retrieved_at_utc: str
    archive_sha256: str
    archive_size_bytes: int
    members: tuple[SecBulkMember, ...]
    lineage_hash: str
    snapshot_id: str

    def lineage_payload(self) -> dict[str, object]:
        return {
            "kind": SNAPSHOT_KIND,
            "raw_contract_version": RAW_SNAPSHOT_CONTRACT_VERSION,
            "year": self.year,
            "quarter": self.quarter,
            "source_url": self.source_url,
            "git_commit": self.git_commit,
            "retrieved_at_utc": self.retrieved_at_utc,
            "archive_sha256": self.archive_sha256,
            "archive_size_bytes": self.archive_size_bytes,
            "members": [member.to_payload() for member in self.members],
        }

    def to_payload(self) -> dict[str, object]:
        return {
            **self.lineage_payload(),
            "lineage_hash": self.lineage_hash,
            "snapshot_id": self.snapshot_id,
        }


@dataclass(frozen=True)
class LoadedSecBulkSnapshot:
    identity: SecBulkSnapshotIdentity
    archive_bytes: bytes


def _compression_name(value: int) -> str:
    if value == zipfile.ZIP_STORED:
        return "stored"
    if value == zipfile.ZIP_DEFLATED:
        return "deflated"
    raise SecBulkSnapshotError("REFUSED: ZIP member uses unsupported compression")


def _validate_member_name(info: zipfile.ZipInfo) -> None:
    name = info.filename
    original_name = info.orig_filename
    if (
        not isinstance(name, str)
        or not name
        or original_name != name
        or "\x00" in original_name
        or name != name.strip()
        or "\\" in name
        or "/" in name
        or Path(name).name != name
        or info.is_dir()
    ):
        raise SecBulkSnapshotError("REFUSED: ZIP member name is unsafe or nested")
    mode = info.external_attr >> 16
    if stat.S_IFMT(mode) == stat.S_IFLNK:
        raise SecBulkSnapshotError("REFUSED: ZIP symlink members are prohibited")
    if stat.S_IFMT(mode) not in {0, stat.S_IFREG}:
        raise SecBulkSnapshotError(
            "REFUSED: ZIP member must represent a regular file"
        )
    if info.flag_bits & 0x1:
        raise SecBulkSnapshotError("REFUSED: encrypted ZIP members are prohibited")


def _hash_text_member(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo
) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")
    size_bytes = 0
    crc32 = 0
    try:
        with archive.open(info, "r") as member:
            while True:
                chunk = member.read(1024 * 1024)
                if not chunk:
                    break
                if b"\x00" in chunk:
                    raise SecBulkSnapshotError(
                        "REFUSED: ZIP table is not UTF-8 text"
                    )
                decoder.decode(chunk, final=False)
                digest.update(chunk)
                crc32 = zlib.crc32(chunk, crc32)
                size_bytes += len(chunk)
                if (
                    size_bytes > info.file_size
                    or size_bytes > MAX_MEMBER_UNCOMPRESSED_BYTES
                ):
                    raise SecBulkSnapshotError(
                        "REFUSED: ZIP member expanded beyond its declared limit"
                    )
        decoder.decode(b"", final=True)
    except SecBulkSnapshotError:
        raise
    except UnicodeDecodeError as exc:
        raise SecBulkSnapshotError("REFUSED: ZIP table is not UTF-8 text") from exc
    except (
        zipfile.BadZipFile,
        RuntimeError,
        NotImplementedError,
        OSError,
        EOFError,
        zlib.error,
    ) as exc:
        raise SecBulkSnapshotError(
            "REFUSED: ZIP table member failed integrity validation"
        ) from exc
    return digest.hexdigest(), size_bytes, crc32 & 0xFFFFFFFF


def _read_archive_members(zip_bytes: bytes) -> tuple[SecBulkMember, ...]:
    if type(zip_bytes) is not bytes or not zip_bytes:
        raise SecBulkSnapshotError("REFUSED: SEC archive must be non-empty bytes")
    if len(zip_bytes) > MAX_ARCHIVE_BYTES:
        raise SecBulkSnapshotError(
            "REFUSED: SEC archive exceeds the compressed-size limit"
        )
    stream = io.BytesIO(zip_bytes)
    try:
        with zipfile.ZipFile(stream, "r") as archive:
            infos = archive.infolist()
            if len(infos) > len(ALLOWED_SEC_TABLES):
                raise SecBulkSnapshotError(
                    "REFUSED: SEC archive contains more than eight tables"
                )
            for info in infos:
                _validate_member_name(info)
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise SecBulkSnapshotError(
                    "REFUSED: ZIP archive contains duplicate member names"
                )
            if len(names) != len({name.casefold() for name in names}):
                raise SecBulkSnapshotError(
                    "REFUSED: ZIP archive contains case-colliding member names"
                )
            missing = sorted(set(REQUIRED_SEC_TABLES) - set(names))
            unexpected = sorted(set(names) - set(ALLOWED_SEC_TABLES))
            if missing or unexpected:
                raise SecBulkSnapshotError(
                    "REFUSED: ZIP table inventory mismatch; "
                    f"missing={missing}, unexpected={unexpected}"
                )

            total_uncompressed = 0
            compression_by_name: dict[str, str] = {}
            for info in infos:
                if info.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
                    raise SecBulkSnapshotError(
                        "REFUSED: ZIP member exceeds the expanded-size limit"
                    )
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
                    raise SecBulkSnapshotError(
                        "REFUSED: ZIP archive exceeds the total expanded-size limit"
                    )
                if info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO:
                    raise SecBulkSnapshotError(
                        "REFUSED: ZIP member exceeds the compression-ratio limit"
                    )
                compression_by_name[info.filename] = _compression_name(
                    info.compress_type
                )

            by_name: dict[str, SecBulkMember] = {}
            for info in infos:
                member_hash, size_bytes, crc32 = _hash_text_member(archive, info)
                if size_bytes != info.file_size:
                    raise SecBulkSnapshotError(
                        "REFUSED: ZIP table member size disagrees with metadata"
                    )
                if crc32 != info.CRC:
                    raise SecBulkSnapshotError(
                        "REFUSED: ZIP table member failed CRC validation"
                    )
                by_name[info.filename] = SecBulkMember(
                    name=info.filename,
                    sha256=member_hash,
                    size_bytes=size_bytes,
                    compressed_size_bytes=info.compress_size,
                    crc32=f"{info.CRC:08x}",
                    compression=compression_by_name[info.filename],
                )
    except (zipfile.BadZipFile, OSError, EOFError) as exc:
        raise SecBulkSnapshotError(
            "REFUSED: malformed or corrupt SEC ZIP archive"
        ) from exc

    return tuple(by_name[name] for name in ALLOWED_SEC_TABLES if name in by_name)


def inspect_sec_bulk_archive(
    zip_bytes: bytes, source: SecBulkSource
) -> SecBulkSnapshotIdentity:
    """Validate one exact byte image and derive its immutable identity."""

    if type(source) is not SecBulkSource:
        raise SecBulkSnapshotError("REFUSED: source metadata contract is required")
    members = _read_archive_members(zip_bytes)
    lineage = {
        "kind": SNAPSHOT_KIND,
        "raw_contract_version": RAW_SNAPSHOT_CONTRACT_VERSION,
        "year": source.year,
        "quarter": source.quarter,
        "source_url": source.source_url,
        "git_commit": source.git_commit,
        "retrieved_at_utc": source.retrieved_at_utc,
        "archive_sha256": hash_bytes(zip_bytes),
        "archive_size_bytes": len(zip_bytes),
        "members": [member.to_payload() for member in members],
    }
    lineage_hash = hash_payload(lineage)
    return SecBulkSnapshotIdentity(
        year=source.year,
        quarter=source.quarter,
        source_url=source.source_url,
        git_commit=source.git_commit,
        retrieved_at_utc=source.retrieved_at_utc,
        archive_sha256=lineage["archive_sha256"],
        archive_size_bytes=len(zip_bytes),
        members=members,
        lineage_hash=lineage_hash,
        snapshot_id=(
            f"sec-insider-bulk-{source.year:04d}q{source.quarter}-"
            f"{lineage_hash[:16]}"
        ),
    )


def _canonical_json_bytes(payload: dict[str, object]) -> bytes:
    return (canonical_json(payload) + "\n").encode("utf-8")


def _status_is_redirect(status: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(status, "st_file_attributes", 0)
    return stat.S_ISLNK(status.st_mode) or bool(
        reparse_flag and file_attributes & reparse_flag
    )


def _require_regular_directory(
    path: Path, *, label: str, missing_ok: bool = False
) -> bool:
    try:
        status = path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return False
        raise SecBulkSnapshotError(f"REFUSED: {label} is missing") from None
    except OSError as exc:
        raise SecBulkSnapshotError(f"REFUSED: {label} is unreadable") from exc
    if _status_is_redirect(status) or not stat.S_ISDIR(status.st_mode):
        raise SecBulkSnapshotError(
            f"REFUSED: {label} must be a non-redirected directory"
        )
    return True


def _same_file_identity(first: os.stat_result, second: os.stat_result) -> bool:
    return first.st_dev == second.st_dev and first.st_ino == second.st_ino


def _same_file_version(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        _same_file_identity(first, second)
        and first.st_size == second.st_size
        and first.st_mtime_ns == second.st_mtime_ns
    )


def _read_regular_bytes(
    path: Path, *, label: str, max_bytes: int | None = None
) -> bytes:
    try:
        before = path.lstat()
        if _status_is_redirect(before) or not stat.S_ISREG(before.st_mode):
            raise SecBulkSnapshotError(
                f"REFUSED: {label} must be a regular immutable file"
            )
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                _status_is_redirect(opened)
                or not stat.S_ISREG(opened.st_mode)
                or not _same_file_identity(before, opened)
            ):
                raise SecBulkSnapshotError(
                    f"REFUSED: {label} changed while it was opened"
                )
            if max_bytes is not None and opened.st_size > max_bytes:
                raise SecBulkSnapshotError(
                    f"REFUSED: {label} exceeds its byte-size limit"
                )
            raw = handle.read() if max_bytes is None else handle.read(max_bytes + 1)
            after_read = os.fstat(handle.fileno())
        after_path = path.lstat()
        if not _same_file_version(opened, after_read) or not _same_file_version(
            after_read, after_path
        ):
            raise SecBulkSnapshotError(
                f"REFUSED: {label} changed while it was read"
            )
        if len(raw) != after_read.st_size:
            raise SecBulkSnapshotError(
                f"REFUSED: {label} was not read as one complete byte image"
            )
        if max_bytes is not None and len(raw) > max_bytes:
            raise SecBulkSnapshotError(
                f"REFUSED: {label} exceeds its byte-size limit"
            )
        return raw
    except SecBulkSnapshotError:
        raise
    except OSError as exc:
        raise SecBulkSnapshotError(
            f"REFUSED: {label} is missing or unreadable"
        ) from exc


def _parse_canonical_object(raw: bytes, *, label: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
        canonical = _canonical_json_bytes(value) if isinstance(value, dict) else None
    except (TypeError, ValueError) as exc:
        raise SecBulkSnapshotError(f"REFUSED: {label} is missing or invalid") from exc
    if not isinstance(value, dict) or raw != canonical:
        raise SecBulkSnapshotError(f"REFUSED: {label} is not canonical JSON")
    return value


def _read_canonical_object(
    path: Path, *, label: str, max_bytes: int
) -> dict[str, object]:
    raw = _read_regular_bytes(path, label=label, max_bytes=max_bytes)
    return _parse_canonical_object(raw, label=label)


def _source_from_manifest(manifest: dict[str, object]) -> SecBulkSource:
    if set(manifest) != _MANIFEST_KEYS:
        raise SecBulkSnapshotError("REFUSED: snapshot manifest fields are not exact")
    retrieved = manifest.get("retrieved_at_utc")
    if not isinstance(retrieved, str):
        raise SecBulkSnapshotError("REFUSED: manifest retrieval time is invalid")
    try:
        retrieved_at = datetime.fromisoformat(retrieved)
    except ValueError as exc:
        raise SecBulkSnapshotError(
            "REFUSED: manifest retrieval time is invalid"
        ) from exc
    source = SecBulkSource(
        year=manifest.get("year"),
        quarter=manifest.get("quarter"),
        source_url=manifest.get("source_url"),
        git_commit=manifest.get("git_commit"),
        retrieved_at=retrieved_at,
    )
    if source.retrieved_at_utc != retrieved:
        raise SecBulkSnapshotError(
            "REFUSED: manifest retrieval time is not UTC canonical"
        )
    return source


def _prepare_output_root(output_root: str | Path) -> Path:
    try:
        root = Path(output_root)
        existed = _require_regular_directory(
            root, label="snapshot output root", missing_ok=True
        )
        if not existed:
            root.mkdir(parents=True, exist_ok=True)
        _require_regular_directory(root, label="snapshot output root")
        canonical_root = root.resolve(strict=True)
        _require_regular_directory(canonical_root, label="snapshot output root")
        return canonical_root
    except SecBulkSnapshotError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise SecBulkSnapshotError(
            "REFUSED: snapshot output root is invalid or unavailable"
        ) from exc


def _require_regular_lock_slot(lock_path: Path) -> None:
    try:
        status = lock_path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise SecBulkSnapshotError(
            "REFUSED: snapshot publication lock is unreadable"
        ) from exc
    if _status_is_redirect(status) or not stat.S_ISREG(status.st_mode):
        raise SecBulkSnapshotError(
            "REFUSED: snapshot publication lock must be a regular file"
        )


def _clean_publisher_temporaries(
    target: Path, expected_files: tuple[tuple[str, bytes], ...]
) -> None:
    """Remove only a wholly verified set of publisher temporaries.

    Verification is deliberately two-phase: no exact residue is removed until
    every directory entry has been classified.  An unexpected or mismatched
    entry therefore cannot cause a partially cleaned state that hides evidence
    from the caller.
    """

    failures: list[str] = []
    verified_temporaries: list[Path] = []
    try:
        leftovers = tuple(target.iterdir())
    except OSError:
        failures.append(str(target))
        leftovers = ()
    final_names = {name for name, _ in expected_files}
    for path in leftovers:
        if path.name in final_names:
            continue
        matched = next(
            (
                (name, expected)
                for name, expected in expected_files
                if path.name.startswith(f".{name}.")
                and path.name.endswith(".tmp")
            ),
            None,
        )
        if matched is None:
            failures.append(path.name)
            continue
        name, expected = matched
        try:
            status = path.lstat()
            if (
                _status_is_redirect(status)
                or not stat.S_ISREG(status.st_mode)
                or _read_regular_bytes(
                    path, label=f"partial temporary {name}", max_bytes=len(expected)
                )
                != expected
            ):
                failures.append(path.name)
                continue
            verified_temporaries.append(path)
        except (OSError, SecBulkSnapshotError):
            failures.append(path.name)
    if failures:
        raise SecBulkSnapshotError(
            "REFUSED: failed publication left unverified files: "
            + ", ".join(sorted(set(failures)))
        )
    unlink_failures: list[str] = []
    for path in verified_temporaries:
        try:
            path.unlink()
        except OSError:
            unlink_failures.append(path.name)
    if unlink_failures:
        raise SecBulkSnapshotError(
            "REFUSED: failed publication left unverified files: "
            + ", ".join(sorted(set(unlink_failures)))
        )


def _rollback_uncommitted_publication(
    target: Path, expected_files: tuple[tuple[str, bytes], ...]
) -> None:
    """Remove a verified interrupted set after classifying all residue.

    Final-name members must be byte-exact.  A recognized publisher temporary
    may be an exact prefix because process death can occur after ``mkstemp``
    or during its sequential write, before the create-exclusive link.  This
    relaxation is deliberately unavailable once a commit marker exists.
    """

    expected_by_name = dict(expected_files)
    failures: list[str] = []
    verified_paths: list[Path] = []
    try:
        leftovers = tuple(target.iterdir())
    except OSError:
        failures.append(str(target))
        leftovers = ()
    for path in leftovers:
        expected = expected_by_name.get(path.name)
        is_final = expected is not None
        if expected is None:
            matched_name = next(
                (
                    name
                    for name in expected_by_name
                    if path.name.startswith(f".{name}.")
                    and path.name.endswith(".tmp")
                ),
                None,
            )
            if matched_name is None:
                failures.append(path.name)
                continue
            expected = expected_by_name[matched_name]
        try:
            status = path.lstat()
        except OSError:
            failures.append(path.name)
            continue
        try:
            actual = _read_regular_bytes(
                path, label=f"partial {path.name}", max_bytes=len(expected)
            )
            if (
                _status_is_redirect(status)
                or not stat.S_ISREG(status.st_mode)
                or (
                    actual != expected
                    and (is_final or not expected.startswith(actual))
                )
            ):
                failures.append(path.name)
                continue
            verified_paths.append(path)
        except (OSError, SecBulkSnapshotError):
            failures.append(path.name)
    if failures:
        raise SecBulkSnapshotError(
            "REFUSED: failed publication left unverified files: "
            + ", ".join(sorted(set(failures)))
        )
    unlink_failures: list[str] = []
    for path in reversed(verified_paths):
        try:
            path.unlink()
        except OSError:
            unlink_failures.append(path.name)
    if unlink_failures:
        raise SecBulkSnapshotError(
            "REFUSED: failed publication left unverified files: "
            + ", ".join(sorted(set(unlink_failures)))
        )


def _recover_committed_publication(
    target: Path,
    expected_files: tuple[tuple[str, bytes], ...],
    identity: SecBulkSnapshotIdentity,
    zip_bytes: bytes,
) -> LoadedSecBulkSnapshot | None:
    try:
        (target / _COMMIT_NAME).lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SecBulkSnapshotError(
            "REFUSED: commit-marker state is unreadable after publication failure"
        ) from exc

    _clean_publisher_temporaries(target, expected_files)
    loaded = load_sec_bulk_snapshot(target)
    if loaded.identity != identity or loaded.archive_bytes != zip_bytes:
        raise SecBulkSnapshotError(
            "REFUSED: committed snapshot conflicts with attempted publication"
        )
    return loaded


def _settle_failed_publication(
    target: Path,
    expected_files: tuple[tuple[str, bytes], ...],
    identity: SecBulkSnapshotIdentity,
    zip_bytes: bytes,
) -> LoadedSecBulkSnapshot | None:
    recovered = _recover_committed_publication(
        target, expected_files, identity, zip_bytes
    )
    if recovered is None:
        _rollback_uncommitted_publication(target, expected_files)
    return recovered


def write_sec_bulk_snapshot(
    zip_bytes: bytes,
    source: SecBulkSource,
    output_root: str | Path,
) -> SecBulkSnapshotIdentity:
    """Publish one complete lineage-addressed set; commit marker is last."""

    identity = inspect_sec_bulk_archive(zip_bytes, source)
    root = _prepare_output_root(output_root)
    target = root / identity.snapshot_id
    manifest_bytes = _canonical_json_bytes(identity.to_payload())
    payloads = {
        _ARCHIVE_NAME: zip_bytes,
        _MANIFEST_NAME: manifest_bytes,
    }
    commit_payload = {
        "kind": f"{SNAPSHOT_KIND}-commit",
        "snapshot_id": identity.snapshot_id,
        "members": {
            name: hash_bytes(data) for name, data in sorted(payloads.items())
        },
    }
    commit_bytes = _canonical_json_bytes(commit_payload)
    publication = tuple(payloads.items()) + ((_COMMIT_NAME, commit_bytes),)
    lock_path = root / f".{identity.snapshot_id}{_LOCK_SUFFIX}"
    _require_regular_lock_slot(lock_path)
    with _SnapshotPublicationLock(lock_path):
        _require_regular_directory(root, label="snapshot output root")
        _require_regular_lock_slot(lock_path)
        if not _require_regular_directory(
            target, label="snapshot target", missing_ok=True
        ):
            try:
                target.mkdir()
            except OSError as exc:
                raise SecBulkSnapshotError(
                    "REFUSED: snapshot target could not be created"
                ) from exc
            _require_regular_directory(target, label="snapshot target")
        try:
            existing = {path.name for path in target.iterdir()}
        except OSError as exc:
            raise SecBulkSnapshotError(
                "REFUSED: snapshot target is unreadable"
            ) from exc
        if _COMMIT_NAME in existing:
            loaded = _recover_committed_publication(
                target, publication, identity, zip_bytes
            )
            if loaded is None:
                raise SecBulkSnapshotError(
                    "REFUSED: commit marker disappeared during verified retry"
                )
            return loaded.identity
        if existing:
            _rollback_uncommitted_publication(target, publication)
        try:
            for name, data in payloads.items():
                publish_immutable_bytes(target / name, data)
            publish_immutable_bytes(target / _COMMIT_NAME, commit_bytes)
            loaded = load_sec_bulk_snapshot(target)
            if loaded.identity != identity or loaded.archive_bytes != zip_bytes:
                raise SecBulkSnapshotError(
                    "REFUSED: published snapshot failed final integrity check"
                )
        except SecBulkSnapshotError as exc:
            try:
                recovered = _settle_failed_publication(
                    target, publication, identity, zip_bytes
                )
            except SecBulkSnapshotError as recovery_exc:
                raise recovery_exc from exc
            if recovered is not None:
                return recovered.identity
            raise
        except (ImmutableFileConflictError, OSError) as exc:
            try:
                recovered = _settle_failed_publication(
                    target, publication, identity, zip_bytes
                )
            except SecBulkSnapshotError as recovery_exc:
                raise SecBulkSnapshotError(
                    "REFUSED: immutable snapshot recovery failed"
                ) from recovery_exc
            if recovered is not None:
                return recovered.identity
            raise SecBulkSnapshotError(
                "REFUSED: immutable snapshot publication conflicted or failed"
            ) from exc
        except BaseException as exc:
            try:
                _settle_failed_publication(
                    target, publication, identity, zip_bytes
                )
            except SecBulkSnapshotError as recovery_exc:
                raise recovery_exc from exc
            raise
    return loaded.identity


def load_sec_bulk_snapshot(snapshot_directory: str | Path) -> LoadedSecBulkSnapshot:
    """Integrity-check a committed raw snapshot before returning its ZIP bytes."""

    directory = Path(snapshot_directory)
    if not _SNAPSHOT_ID_RE.fullmatch(directory.name):
        raise SecBulkSnapshotError("REFUSED: snapshot directory name is invalid")
    _require_regular_directory(directory, label="snapshot directory")
    try:
        names = {path.name for path in directory.iterdir()}
    except OSError as exc:
        raise SecBulkSnapshotError("REFUSED: snapshot directory is unreadable") from exc
    allowed = {_ARCHIVE_NAME, _MANIFEST_NAME, _COMMIT_NAME}
    if _COMMIT_NAME not in names:
        raise SecBulkSnapshotError(
            "REFUSED: immutable snapshot is incomplete; commit marker is missing"
        )
    if names != allowed:
        raise SecBulkSnapshotError(
            "REFUSED: snapshot directory has missing or unexpected files"
        )

    commit = _read_canonical_object(
        directory / _COMMIT_NAME,
        label="commit marker",
        max_bytes=MAX_COMMIT_BYTES,
    )
    if set(commit) != {"kind", "snapshot_id", "members"}:
        raise SecBulkSnapshotError("REFUSED: commit marker fields are not exact")
    if (
        commit.get("kind") != f"{SNAPSHOT_KIND}-commit"
        or commit.get("snapshot_id") != directory.name
        or not isinstance(commit.get("members"), dict)
        or set(commit["members"]) != {_ARCHIVE_NAME, _MANIFEST_NAME}
    ):
        raise SecBulkSnapshotError("REFUSED: commit marker identity is invalid")

    archive_bytes = _read_regular_bytes(
        directory / _ARCHIVE_NAME,
        label="committed archive",
        max_bytes=MAX_ARCHIVE_BYTES,
    )
    manifest_bytes = _read_regular_bytes(
        directory / _MANIFEST_NAME,
        label="committed manifest",
        max_bytes=MAX_MANIFEST_BYTES,
    )
    actual_commit_members = {
        _ARCHIVE_NAME: hash_bytes(archive_bytes),
        _MANIFEST_NAME: hash_bytes(manifest_bytes),
    }
    if commit["members"] != actual_commit_members:
        raise SecBulkSnapshotError("REFUSED: committed snapshot member hash mismatch")

    manifest = _parse_canonical_object(manifest_bytes, label="manifest")
    source = _source_from_manifest(manifest)
    if manifest.get("kind") != SNAPSHOT_KIND:
        raise SecBulkSnapshotError("REFUSED: snapshot manifest kind is invalid")
    if (
        type(manifest.get("raw_contract_version")) is not int
        or manifest.get("raw_contract_version")
        != RAW_SNAPSHOT_CONTRACT_VERSION
    ):
        raise SecBulkSnapshotError("REFUSED: snapshot contract version is unsupported")
    members_payload = manifest.get("members")
    if not isinstance(members_payload, list):
        raise SecBulkSnapshotError("REFUSED: snapshot member inventory is invalid")
    recorded_members = tuple(
        SecBulkMember.from_payload(payload) for payload in members_payload
    )
    recorded_names = tuple(member.name for member in recorded_members)
    canonical_names = tuple(
        name for name in ALLOWED_SEC_TABLES if name in set(recorded_names)
    )
    if (
        recorded_names != canonical_names
        or not set(REQUIRED_SEC_TABLES) <= set(recorded_names)
    ):
        raise SecBulkSnapshotError("REFUSED: snapshot member order is not canonical")
    if (
        not isinstance(manifest.get("archive_sha256"), str)
        or not _SHA256_RE.fullmatch(manifest["archive_sha256"])
        or type(manifest.get("archive_size_bytes")) is not int
        or not isinstance(manifest.get("lineage_hash"), str)
        or not _SHA256_RE.fullmatch(manifest["lineage_hash"])
        or not isinstance(manifest.get("snapshot_id"), str)
    ):
        raise SecBulkSnapshotError("REFUSED: snapshot identity fields are invalid")

    rebuilt = inspect_sec_bulk_archive(archive_bytes, source)
    if manifest != rebuilt.to_payload():
        raise SecBulkSnapshotError(
            "REFUSED: snapshot manifest does not integrity-check the raw archive"
        )
    if rebuilt.snapshot_id != directory.name:
        raise SecBulkSnapshotError(
            "REFUSED: snapshot directory does not match lineage identity"
        )
    return LoadedSecBulkSnapshot(identity=rebuilt, archive_bytes=archive_bytes)


__all__ = [
    "ALLOWED_SEC_TABLES",
    "LoadedSecBulkSnapshot",
    "SecBulkMember",
    "SecBulkSnapshotError",
    "SecBulkSnapshotIdentity",
    "SecBulkSource",
    "REQUIRED_SEC_TABLES",
    "inspect_sec_bulk_archive",
    "load_sec_bulk_snapshot",
    "write_sec_bulk_snapshot",
]
