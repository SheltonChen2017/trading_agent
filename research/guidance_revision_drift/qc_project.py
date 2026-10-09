"""Bounded Python-only carrier preparation, not native/cloud certification.

The current deterministic source archive is encoded without compression. Local
preparation and verification only return detached bytes and identities; the
generated root loader is inert text here. Its new runtime packaging behavior
requires fresh exact-source review before any authorized synthetic QC launch.
"""
from __future__ import annotations

import base64
from io import BytesIO
import re
from zipfile import ZipFile

from data.hashing import hash_bytes, hash_payload
from research.guidance_revision_drift.bundle import (
    BundleError, MANIFEST_PATH, SIDECAR_PATH, build_bundle, verify_bundle,
)


MAX_PROJECT_FILES = 25
MAX_PROJECT_FILE_BYTES = 32_000  # Every file must be strictly smaller.
PAYLOAD_CHARS = 30_000
_PAYLOAD_PREFIX = "gdr_payload_"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_PAYLOAD_NAME = re.compile(r"gdr_payload_[0-9]{3}\.py\Z")


class QCProjectError(ValueError):
    """An unsafe, changed or oversized synthetic project carrier."""


# This string is prepared as source, never imported by the local generator.
# Payload files are read as a single AST string constant, never as modules.
_ROOT_TEMPLATE = '''"""Reviewed synthetic-only source carrier; no empirical readiness claim."""
import ast
import base64
import hashlib
from io import BytesIO
import os
from pathlib import Path
import stat
import sys
import tempfile
from zipfile import BadZipFile, ZIP_STORED, ZipFile, ZipInfo


_GDR_EXPECTED_BUNDLE_SHA256 = __BUNDLE_SHA256__
_GDR_EXPECTED_BUNDLE_BYTES = __BUNDLE_BYTES__
_GDR_EXPECTED_PAYLOAD_FILES = __PAYLOAD_FILES__
_GDR_EXPECTED_MEMBERS = __MEMBERS__
_GDR_MAX_PROJECT_FILE_BYTES = 32000
_GDR_PAYLOAD_CHARS = 30000
_GDR_DATE = (1980, 1, 1, 0, 0, 0)
_GDR_FILE_MODE = (stat.S_IFREG | 0o444) << 16


def _gdr_refuse(message):
    raise RuntimeError("GDR carrier refused: " + message)


def _gdr_read_regular(path, expected_size):
    if (type(expected_size) is not int or not 0 < expected_size
            < _GDR_MAX_PROJECT_FILE_BYTES):
        _gdr_refuse("invalid payload file bound")
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size != expected_size:
            _gdr_refuse("payload must be an exact bounded regular file")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode) or opened.st_size != expected_size
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
                _gdr_refuse("payload file changed during open")
            chunks = []
            remaining = expected_size + 1
            while remaining:
                chunk = os.read(descriptor, remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise RuntimeError("GDR carrier refused: payload file unavailable") from exc
    if len(raw) != expected_size:
        _gdr_refuse("payload file size changed during read")
    return raw


def _gdr_payload(project_root):
    if (type(_GDR_EXPECTED_BUNDLE_BYTES) is not int
            or not 0 < _GDR_EXPECTED_BUNDLE_BYTES <= 540000):
        _gdr_refuse("invalid archive size bound")
    expected_names = tuple(row[0] for row in _GDR_EXPECTED_PAYLOAD_FILES)
    if (not 1 <= len(expected_names) <= 24
            or expected_names != tuple("gdr_payload_%03d.py" % i
                                       for i in range(len(expected_names)))):
        _gdr_refuse("invalid ordered payload inventory")
    observed_names = []
    # Inspect only names, not unrelated file contents. Bound directory traversal.
    with os.scandir(project_root) as entries:
        for index, entry in enumerate(entries):
            if index >= 1024:
                _gdr_refuse("project directory inventory exceeds bound")
            if entry.name.startswith("gdr_payload_"):
                observed_names.append(entry.name)
                if len(observed_names) > 24:
                    _gdr_refuse("extra payload file")
            elif entry.name.endswith(".py") and entry.name != "main.py":
                _gdr_refuse("unexpected project Python file")
    if tuple(sorted(observed_names)) != expected_names:
        _gdr_refuse("missing or extra payload file")
    encoded_parts = []
    for index, (name, size, digest) in enumerate(_GDR_EXPECTED_PAYLOAD_FILES):
        raw = _gdr_read_regular(project_root / name, size)
        if hashlib.sha256(raw).hexdigest() != digest:
            _gdr_refuse("payload file differs from retained identity")
        try:
            tree = ast.parse(raw.decode("ascii"), filename=name)
        except (UnicodeError, SyntaxError, ValueError, RecursionError) as exc:
            raise RuntimeError("GDR carrier refused: invalid payload syntax") from exc
        if len(tree.body) != 1 or type(tree.body[0]) is not ast.Assign:
            _gdr_refuse("payload must contain one literal assignment")
        assignment = tree.body[0]
        if (len(assignment.targets) != 1 or type(assignment.targets[0]) is not ast.Name
                or assignment.targets[0].id != "_GDR_B64"
                or type(assignment.value) is not ast.Constant
                or type(assignment.value.value) is not str):
            _gdr_refuse("payload must contain one literal string")
        part = assignment.value.value
        if (not 0 < len(part) <= _GDR_PAYLOAD_CHARS
                or (index < len(expected_names) - 1
                    and len(part) != _GDR_PAYLOAD_CHARS)):
            _gdr_refuse("noncanonical payload chunk size")
        encoded_parts.append(part)
    encoded = "".join(encoded_parts)
    if len(encoded) != ((_GDR_EXPECTED_BUNDLE_BYTES + 2) // 3) * 4:
        _gdr_refuse("encoded archive size differs from retained identity")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, UnicodeError) as exc:
        raise RuntimeError("GDR carrier refused: invalid base64 archive") from exc
    if (base64.b64encode(raw).decode("ascii") != encoded
            or len(raw) != _GDR_EXPECTED_BUNDLE_BYTES
            or hashlib.sha256(raw).hexdigest() != _GDR_EXPECTED_BUNDLE_SHA256):
        _gdr_refuse("archive differs from canonical retained identity")
    return raw


def _gdr_members(raw):
    if (not 0 < len(raw) <= 540000 or len(_GDR_EXPECTED_MEMBERS) > 64):
        _gdr_refuse("archive exceeds runtime carrier bound")
    expected_names = tuple(row[0] for row in _GDR_EXPECTED_MEMBERS)
    if (expected_names != tuple(sorted(set(expected_names)))
            or not expected_names):
        _gdr_refuse("invalid expected archive inventory")
    for name in expected_names:
        if (type(name) is not str or name.startswith("/") or "\\\\" in name
                or any(part in ("", ".", "..") for part in name.split("/"))
                or not all(character.isascii() and
                           (character.isalnum() or character in "_/-.")
                           for character in name)):
            _gdr_refuse("unsafe archive member path")
    try:
        with ZipFile(BytesIO(raw), "r", allowZip64=False) as archive:
            infos = archive.infolist()
            if archive.comment or tuple(info.filename for info in infos) != expected_names:
                _gdr_refuse("archive differs from exact ordered member inventory")
            for info, (_, size, _) in zip(infos, _GDR_EXPECTED_MEMBERS):
                if (type(size) is not int or not 0 <= size <= 1048576
                        or info.file_size != size or info.compress_size != size
                        or info.compress_type != ZIP_STORED
                        or info.date_time != _GDR_DATE or info.create_system != 3
                        or info.external_attr != _GDR_FILE_MODE or info.internal_attr
                        or info.flag_bits or info.extra or info.comment):
                    _gdr_refuse("unsafe, oversized or noncanonical archive member")
            if sum(info.file_size for info in infos) > 540000:
                _gdr_refuse("expanded archive exceeds runtime carrier bound")
            members = {}
            for info, (name, size, digest) in zip(infos, _GDR_EXPECTED_MEMBERS):
                content = archive.read(info)
                if len(content) != size or hashlib.sha256(content).hexdigest() != digest:
                    _gdr_refuse("archive member differs from retained identity")
                members[name] = content
        canonical = BytesIO()
        with ZipFile(canonical, "w", compression=ZIP_STORED, allowZip64=False) as archive:
            for name in expected_names:
                info = ZipInfo(name, date_time=_GDR_DATE)
                info.create_system = 3
                info.compress_type = ZIP_STORED
                info.external_attr = _GDR_FILE_MODE
                archive.writestr(info, members[name])
        if canonical.getvalue() != raw:
            _gdr_refuse("noncanonical archive encoding")
        return members
    except (BadZipFile, OSError, ValueError, EOFError) as exc:
        raise RuntimeError("GDR carrier refused: invalid archive") from exc


def _gdr_check_roots():
    if any(name == "data" or name.startswith("data.") or name == "research"
           or name.startswith("research.") for name in tuple(sys.modules)):
        _gdr_refuse("conflicting preloaded data or research package root")


def _gdr_prepare():
    _gdr_check_roots()
    root_file = Path(__file__)
    root_status = root_file.lstat()
    if (not stat.S_ISREG(root_status.st_mode)
            or not 0 < root_status.st_size < _GDR_MAX_PROJECT_FILE_BYTES):
        _gdr_refuse("root loader must be a bounded regular file")
    members = _gdr_members(_gdr_payload(root_file.resolve().parent))
    temporary = tempfile.TemporaryDirectory(prefix="gdr-synthetic-")
    root = Path(temporary.name)
    try:
        directories = set()
        for name in members:
            parts = name.split("/")
            for end in range(1, len(parts)):
                directories.add("/".join(parts[:end]))
        for name in sorted(directories, key=lambda name: (name.count("/"), name)):
            (root / name).mkdir(mode=0o700)
        for name, content in members.items():
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(root / name, flags, 0o444)
            try:
                remaining = memoryview(content)
                while remaining:
                    written = os.write(descriptor, remaining)
                    if written <= 0:
                        _gdr_refuse("cannot materialize complete member")
                    remaining = remaining[written:]
            finally:
                os.close(descriptor)
        _gdr_check_roots()
        sys.path.insert(0, str(root))
        return temporary
    except BaseException:
        temporary.cleanup()
        raise


_GDR_RUNTIME_DIRECTORY = _gdr_prepare()
from research.guidance_revision_drift.lean.main import (
    GuidanceRevisionDriftAlgorithm as _NativeGuidanceRevisionDriftAlgorithm,
)


class GuidanceRevisionDriftAlgorithm(_NativeGuidanceRevisionDriftAlgorithm):
    """Root discovery class; all native callbacks and economics are inherited."""
    pass


del _NativeGuidanceRevisionDriftAlgorithm
'''


def _file_manifest(files: dict[str, bytes]) -> dict[str, dict[str, object]]:
    return {name: {"bytes": len(raw), "sha256": hash_bytes(raw)}
            for name, raw in sorted(files.items())}


def _bounded_files(files: dict[str, bytes]) -> None:
    if type(files) is not dict or not 2 <= len(files) <= MAX_PROJECT_FILES:
        raise QCProjectError("exact bounded project-file dictionary required")
    if ("main.py" not in files
            or any(type(name) is not str or (name != "main.py" and not _PAYLOAD_NAME.fullmatch(name))
                   or type(raw) is not bytes or not 0 < len(raw) < MAX_PROJECT_FILE_BYTES
                   for name, raw in files.items())):
        raise QCProjectError("project requires only bounded Python carrier files")
    names = tuple(sorted(name for name in files if name != "main.py"))
    if names != tuple(_PAYLOAD_PREFIX + "%03d.py" % index for index in range(len(names))):
        raise QCProjectError("missing or noncanonical ordered payload-file inventory")


def _prepare_project() -> tuple[dict[str, bytes], dict]:
    try:
        raw = build_bundle()
        bundle_sha256 = hash_bytes(raw)
        bundle = verify_bundle(raw, expected_sha256=bundle_sha256)
    except BundleError as exc:
        raise QCProjectError("cannot prepare current-source synthetic carrier") from exc
    if len(raw) > PAYLOAD_CHARS * (MAX_PROJECT_FILES - 1) // 4 * 3:
        raise QCProjectError("source bundle exceeds Python carrier capacity")
    encoded = base64.b64encode(raw).decode("ascii")
    files = {}
    for index, start in enumerate(range(0, len(encoded), PAYLOAD_CHARS)):
        name = _PAYLOAD_PREFIX + "%03d.py" % index
        files[name] = ("_GDR_B64 = " + repr(encoded[start:start + PAYLOAD_CHARS]) + "\n").encode("ascii")
    payload_files = tuple((name, len(content), hash_bytes(content))
                          for name, content in sorted(files.items()))
    with ZipFile(BytesIO(raw), "r", allowZip64=False) as archive:
        members = tuple((info.filename, info.file_size, hash_bytes(archive.read(info)))
                        for info in archive.infolist())
    root_source = _ROOT_TEMPLATE
    for token, value in (("__BUNDLE_SHA256__", repr(bundle_sha256)),
                         ("__BUNDLE_BYTES__", repr(len(raw))),
                         ("__PAYLOAD_FILES__", repr(payload_files)),
                         ("__MEMBERS__", repr(members))):
        if root_source.count(token) != 1:
            raise QCProjectError("invalid fixed root-loader template")
        root_source = root_source.replace(token, value)
    files["main.py"] = root_source.encode("ascii")
    _bounded_files(files)
    inventory = _file_manifest(files)
    body = bundle["manifest"]
    fixture = body["members"][SIDECAR_PATH]
    manifest = {
        "schema": "gdr.synthetic.python-project.v1",
        "purpose": "offline_cloud_carrier_preparation_not_native_certification",
        "format": "Python_AST_literal_base64_of_exact_ZIP_STORED_source_bundle",
        "entrypoint": "main.py",
        "native_entrypoint": body["entrypoint"],
        "project_sha256": hash_payload(inventory),
        "project_files": inventory,
        "bundle_sha256": bundle_sha256,
        "bundle_bytes": len(raw),
        "bundle_manifest_member": MANIFEST_PATH,
        "source_manifest_sha256": body["source_manifest_sha256"],
        "candidate_sha256": body["candidate_sha256"],
        "fixture_sha256": fixture["sha256"],
        "fixture_bytes": fixture["bytes"],
        "fixture_frames": 372,
        "runtime_materialization": "new_private_temporary_directory_exclusive_files_only",
        "root_callbacks_overridden": False,
        "fresh_review_required": True,
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
    try:
        # Reject a changed source epoch during carrier/template construction.
        verify_bundle(raw, expected_sha256=bundle_sha256)
    except BundleError as exc:
        raise QCProjectError("source changed while preparing synthetic carrier") from exc
    return files, manifest


def build_qc_project() -> dict[str, bytes]:
    """Return detached deterministic Python file bytes; no write/upload/run."""
    return dict(_prepare_project()[0])


def qc_project_manifest() -> dict:
    """Return fresh source/candidate/fixture/file identities, never approval."""
    return _prepare_project()[1]


def verify_qc_project(files: dict[str, bytes], *, expected_sha256: str) -> dict:
    """Require the caller-retained file-map anchor and current-source replay.

    Only bytes are compared. Generated Python is not imported and no archive
    is materialized. A hash newly asserted by the supplied map is insufficient.
    """
    if type(files) is not dict or not 2 <= len(files) <= MAX_PROJECT_FILES:
        raise QCProjectError("exact bounded project-file dictionary required")
    # The caller may mutate its dictionary during source reconstruction.
    # Retain one private map; validated bytes/str keys are immutable values.
    snapshot = files.copy()
    _bounded_files(snapshot)
    if (type(expected_sha256) is not str or not _DIGEST.fullmatch(expected_sha256)
            or hash_payload(_file_manifest(snapshot)) != expected_sha256):
        raise QCProjectError("project differs from caller-retained file-map anchor")
    expected_files, manifest = _prepare_project()
    if snapshot != expected_files:
        raise QCProjectError("project does not reconstruct from exact current source")
    return {"status": "verified_offline_content_only", **manifest}
