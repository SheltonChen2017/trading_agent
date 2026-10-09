"""Deterministic local source preparation, not a runnable-QC certification.

Only the explicitly inventoried lane source, neutral helpers, pinned draft and
invented sidecar are included. No SDK, credentials, licensed data, downloads,
archive extraction or execution is performed. Verification needs the current
repository source as well as a caller-retained archive anchor; a newly
self-hashed manifest is not evidence. The output directory and its ancestors
must be owner-controlled. Atomic publication is not a portable power-loss or
adversarial-rollback guarantee.
"""
from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
import re
import stat
import struct
import tempfile
from zipfile import BadZipFile, ZIP_STORED, ZipFile, ZipInfo

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.guidance_revision_drift.contracts import (
    Candidate, CandidateError, MAX_CANDIDATE_BYTES, MAX_SOURCE_DOCUMENT_BYTES,
    _decode, _read_regular_file,
)
from research.guidance_revision_drift.lean_bridge import fixture_stream
from research.guidance_revision_drift.reporting import source_manifest


MAX_BUNDLE_BYTES = 4 * 1024 * 1024
MAX_BUNDLE_MEMBERS = 64
MANIFEST_PATH = "gdr-bundle-manifest.json"
SIDECAR_PATH = "research/guidance_revision_drift/lean/gdr-synthetic.jsonl"
_CANDIDATE_PATH = "research/guidance_revision_drift/specs/gdr0a.draft.json"
_ROOT = Path(__file__).resolve().parents[2]
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_PATH = re.compile(r"[A-Za-z0-9_/-]+\.[A-Za-z0-9.]+\Z")
_DATE = (1980, 1, 1, 0, 0, 0)
_FILE_MODE = (stat.S_IFREG | 0o444) << 16
# Deliberate inventory changes require a source change/review. A new arbitrary
# *.py file discovered by source_manifest must not silently enter this bundle.
_MODULES = (
    "__init__", "__main__", "archive", "artifacts", "assessment", "bundle",
    "callback_plan", "comparison", "completion_evidence", "contracts", "controls", "corporate_actions", "evaluation", "events",
    "fixtures", "formulas", "integration", "lean_bridge", "lineage",
    "market_inputs", "paired_bridge", "persistence", "qc_adapter", "qc_project", "readiness", "recovery",
    "release", "reporting", "scenario", "simulation", "specification",
    "timing", "universe", "vendor_payloads", "lean/__init__", "lean/main",
)
_SOURCE_PATHS = frozenset(
    {"research/guidance_revision_drift/" + name + ".py" for name in _MODULES}
    | {_CANDIDATE_PATH, "research/__init__.py", "data/__init__.py",
       "data/hashing.py", "data/financial_primitives.py"}
)


class BundleError(ValueError):
    """Unsafe, incomplete, changed or unverifiable offline source bundle."""


class BundlePublicationUncertain(BundleError):
    """Publication may exist; verify its anchor before retrying, never overwrite."""


def _path(name: str) -> None:
    if (type(name) is not str or not _PATH.fullmatch(name) or name.startswith("/")
            or any(part in ("", ".", "..") for part in name.split("/"))):
        raise BundleError("unsafe archive member path")


def _snapshot() -> tuple[dict[str, bytes], dict]:
    """Read a bounded inventory; detect a changed source epoch during the read."""
    try:
        sources = source_manifest()
        if set(sources) != _SOURCE_PATHS:
            raise BundleError("source manifest differs from explicit bundle inventory")
        members = {}
        for name in sorted(_SOURCE_PATHS):
            _path(name)
            raw = _read_regular_file(_ROOT / name, MAX_SOURCE_DOCUMENT_BYTES)
            if hash_bytes(raw) != sources[name]:
                raise BundleError("source changed while preparing bundle")
            members[name] = raw
        candidate = Candidate.from_bytes(members[_CANDIDATE_PATH])
        members[SIDECAR_PATH] = fixture_stream()
        if source_manifest() != sources:
            raise BundleError("source changed while preparing bundle")
        if (len(members) + 1 > MAX_BUNDLE_MEMBERS
                or sum(map(len, members.values())) > MAX_BUNDLE_BYTES // 2
                or any(len(raw) > MAX_SOURCE_DOCUMENT_BYTES for raw in members.values())):
            raise BundleError("bundle source inventory exceeds bounded limits")
        manifest = {
            "schema": "gdr.synthetic.source-bundle.v1",
            "purpose": "local_source_preparation_not_QC_runtime_certification",
            "format": "ZIP_STORED_fixed_1980_UNIX_regular_0444_sorted_no_extra_metadata",
            "layout": "repository_relative_no_automatic_extraction",
            "entrypoint": "research/guidance_revision_drift/lean/main.py",
            "candidate_sha256": candidate.sha256,
            "source_manifest_sha256": hash_payload(sources),
            "source_manifest": sources,
            "members": {name: {"sha256": hash_bytes(raw), "bytes": len(raw)}
                        for name, raw in sorted(members.items())},
            "manifest_member": MANIFEST_PATH,
            "planning_documents_included": False,
            "SDK_included": False,
            "native_runtime_verified": False,
            "QC_completed": False,
            "qc_upload_allowed": False,
            "qc_launch_allowed": False,
            "provider_access_allowed": False,
            "paper_live_allowed": False,
            "market_evidence": False,
            "point_in_time_evidence": False,
        }
        _decode(canonical_json(manifest).encode("utf-8"))
        return members, manifest
    except CandidateError as exc:
        raise BundleError("invalid bounded source/candidate inventory") from exc


def bundle_manifest() -> dict:
    """A fresh current-source projection, not an approval or archive anchor."""
    return _snapshot()[1]


def _archive(members: dict[str, bytes]) -> bytes:
    destination = BytesIO()
    with ZipFile(destination, "w", compression=ZIP_STORED, allowZip64=False) as archive:
        for name, raw in sorted(members.items()):
            info = ZipInfo(name, date_time=_DATE)
            info.create_system = 3
            info.compress_type = ZIP_STORED
            info.external_attr = _FILE_MODE
            archive.writestr(info, raw)
    raw = destination.getvalue()
    if len(raw) > MAX_BUNDLE_BYTES:
        raise BundleError("bundle exceeds archive byte limit")
    return raw


def build_bundle() -> bytes:
    """Return deterministic bytes only; do not write, launch or extract them."""
    members, manifest = _snapshot()
    return _archive(members | {MANIFEST_PATH: canonical_json(manifest).encode("utf-8")})


def verify_bundle(raw: bytes, *, expected_sha256: str) -> dict:
    """Validate strict inventory/content against the retained hash and source.

    Refuse compression before reading members, so advertised expanded sizes
    cannot induce decompression. Exact re-encoding also rejects hidden local
    headers, trailing/prepended bytes and noncanonical ZIP representations.
    Nothing is extracted or imported from the archive.
    """
    if type(raw) is not bytes or not raw or len(raw) > MAX_BUNDLE_BYTES:
        raise BundleError("nonempty bounded bundle bytes required")
    if (type(expected_sha256) is not str or not _DIGEST.fullmatch(expected_sha256)
            or hash_bytes(raw) != expected_sha256):
        raise BundleError("bundle differs from caller-retained archive anchor")
    allowed = _SOURCE_PATHS | {SIDECAR_PATH, MANIFEST_PATH}
    try:
        with ZipFile(BytesIO(raw), "r", allowZip64=False) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if (archive.comment or len(infos) > MAX_BUNDLE_MEMBERS
                    or len(names) != len(set(names)) or set(names) != allowed
                    or names != sorted(names)):
                raise BundleError("archive differs from exact ordered member inventory")
            for info in infos:
                _path(info.filename)
                limit = MAX_CANDIDATE_BYTES if info.filename == MANIFEST_PATH else MAX_SOURCE_DOCUMENT_BYTES
                if (info.compress_type != ZIP_STORED or info.compress_size != info.file_size
                        or not 0 <= info.file_size <= limit or info.date_time != _DATE
                        or info.create_system != 3 or info.external_attr != _FILE_MODE
                        or info.internal_attr or info.flag_bits or info.extra or info.comment):
                    raise BundleError("unsafe, oversized or noncanonical archive member")
            if sum(info.file_size for info in infos) > MAX_BUNDLE_BYTES:
                raise BundleError("archive expanded size exceeds limit")
            members = {info.filename: archive.read(info) for info in infos}
        body = _decode(members[MANIFEST_PATH])
        if members[MANIFEST_PATH] != canonical_json(body).encode("utf-8"):
            raise BundleError("canonical bundle manifest required")
        expected_members, expected_manifest = _snapshot()
        expected_members[MANIFEST_PATH] = canonical_json(expected_manifest).encode("utf-8")
        if members != expected_members:
            raise BundleError("bundle does not reproduce from current local source and fixtures")
        if _archive(members) != raw:
            raise BundleError("noncanonical archive encoding")
    except BundleError:
        raise
    except (BadZipFile, OSError, RuntimeError, NotImplementedError, EOFError,
            struct.error, ValueError) as exc:
        raise BundleError("invalid bounded source archive") from exc
    return {"status": "verified_offline_content_only", "sha256": expected_sha256,
            "bytes": len(raw), "manifest": body, "qc_upload_allowed": False,
            "qc_launch_allowed": False, "native_runtime_verified": False,
            "market_evidence": False}


def _sync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_bundle(directory: Path, raw: bytes) -> Path:
    """Atomically publish one content-addressed ZIP, never overwrite a path.

    A failed post-link sync/verification is explicitly ambiguous. Retrying the
    same verified bytes acknowledges an identical existing regular file only.
    Unsupported directory synchronization refuses successful acknowledgement.
    """
    # Validate before making even a staging file. Verification is preparation,
    # not external permission and does not consume a research/QC attempt.
    verify_bundle(raw, expected_sha256=hash_bytes(raw) if type(raw) is bytes else "")
    directory = Path(directory)
    temporary = None
    publication_attempted = False
    published = False
    try:
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise BundleError("existing non-symlink owner-controlled directory required")
        directory = directory.resolve(strict=True)
        destination = directory / (hash_bytes(raw) + ".zip")
        descriptor, temporary = tempfile.mkstemp(prefix=".gdr-bundle-", suffix=".staging", dir=directory)
        try:
            remaining = memoryview(raw)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise OSError("incomplete bundle write")
                remaining = remaining[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            publication_attempted = True
            os.link(temporary, destination)
            published = True
        except FileExistsError:
            if _read_regular_file(destination, MAX_BUNDLE_BYTES) != raw:
                raise BundleError("immutable bundle destination has different bytes")
            published = True
        _sync_directory(directory)
        if _read_regular_file(destination, MAX_BUNDLE_BYTES) != raw:
            raise BundleError("published bundle content verification failed")
        return destination
    except (OSError, CandidateError, BundleError) as exc:
        if published or (publication_attempted and isinstance(exc, OSError)):
            raise BundlePublicationUncertain("bundle publication may exist; verify before retry") from exc
        if isinstance(exc, BundleError):
            raise
        raise BundleError("cannot publish bounded local source bundle") from exc
    finally:
        if temporary is not None:
            # Remove only this call's exclusive staging file, never a bundle.
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass  # A private staging remnant is not a published archive.
