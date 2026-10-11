"""Readable native Python and literal synthetic data; offline preparation only.

No source is encoded, packed, extracted or dynamically executed. The native ZIP
is an offline audit reference, not a cloud carrier. New project identities and
external authorization remain necessary; preparation cannot confer permission.
"""
from __future__ import annotations

import ast
from io import BytesIO
import re
from zipfile import ZipFile

from data.hashing import hash_bytes, hash_payload
from research.guidance_revision_drift.bundle import (
    BundleError, MANIFEST_PATH, SIDECAR_PATH, _CANDIDATE_PATH,
)
from research.guidance_revision_drift.native_bundle import build_native_bundle, verify_native_bundle
from research.guidance_revision_drift.reporting import source_manifest


MAX_PROJECT_FILES = 50
RESERVED_PROJECT_FILES = 1  # Researcher's default research.ipynb.
MAX_PROJECT_FILE_BYTES = 64_000  # Conservative decimal bound, strictly smaller.
ASSET_PATH = "gdr_assets.py"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_PYTHON_PATH = re.compile(r"(?:[A-Za-z_][A-Za-z0-9_]*/)*[A-Za-z_][A-Za-z0-9_]*\.py\Z")


class QCProjectError(ValueError):
    """An unsafe, changed or oversized readable synthetic project."""


# Prepared as visible source; never imported or executed by the local generator.
_ROOT_TEMPLATE = '''"""Readable synthetic-only project; no empirical readiness claim."""
import ast
import hashlib
import os
from pathlib import Path
import stat
import sys
import tempfile


_GDR_EXPECTED_FILES = __FILES__
_GDR_EXPECTED_ASSETS = __ASSETS__
_GDR_MAX_PROJECT_FILE_BYTES = 64000
_GDR_MAX_UNUSED_BYTECODE_BYTES = 262144


def _gdr_refuse(message):
    raise RuntimeError("GDR project refused: " + message)


def _gdr_read_regular(path, expected_size):
    if (type(expected_size) is not int or not 0 <= expected_size
            < _GDR_MAX_PROJECT_FILE_BYTES
            or (expected_size == 0 and path.name != "__init__.py")):
        _gdr_refuse("invalid regular file bound")
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size != expected_size:
            _gdr_refuse("expected exact bounded regular file")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode) or opened.st_size != expected_size
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
                _gdr_refuse("regular file changed during open")
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
        raise RuntimeError("GDR project refused: regular file unavailable") from exc
    if len(raw) != expected_size:
        _gdr_refuse("regular file size changed during read")
    return raw


def _gdr_check_roots():
    if any(name in {"data", "research", "gdr_assets"}
           or name.startswith(("data.", "research.", "gdr_assets."))
           for name in tuple(sys.modules)):
        _gdr_refuse("conflicting preloaded project package")


def _gdr_inventory(project_root):
    names = tuple(row[0] for row in _GDR_EXPECTED_FILES)
    if (not 1 <= len(names) <= 48 or names != tuple(sorted(set(names)))
            or len({name.casefold() for name in names}) != len(names)):
        _gdr_refuse("invalid exact project inventory")
    expected_directories = {""}
    for name in names:
        if (type(name) is not str or name.startswith("/") or "\\\\" in name
                or not name.endswith(".py")
                or any(not part.isascii() or not part.isidentifier()
                       for part in name[:-3].split("/"))):
            _gdr_refuse("unsafe project path")
        parts = name.split("/")
        for end in range(1, len(parts)):
            expected_directories.add("/".join(parts[:end]))
    # Traverse only named project package directories, never platform internals.
    for name in sorted(expected_directories):
        directory = project_root / name
        if (not stat.S_ISDIR(directory.lstat().st_mode)
                or directory.resolve() != directory):
            _gdr_refuse("redirected project directory")
        expected_python = {Path(path).name for path in names
                           if str(Path(path).parent) == (name or ".")}
        if not name:
            expected_python.add("main.py")
        expected_children = {Path(path).name for path in expected_directories
                             if path and str(Path(path).parent) == (name or ".")}
        observed_python = set()
        with os.scandir(directory) as entries:
            for index, entry in enumerate(entries):
                if index >= 1024:
                    _gdr_refuse("project directory inventory exceeds bound")
                if (entry.name.isidentifier() and entry.name != "__pycache__"
                        and entry.name not in expected_children
                        and (entry.is_dir(follow_symlinks=False) or entry.is_symlink())):
                    _gdr_refuse("unlisted importable project directory")
                if entry.name.endswith(".pyc"):
                    # QC's loader supplies adjacent compiled copies, including
                    # main.pyc. Permit only bounded regular counterparts of
                    # named visible source. Never read or execute these here;
                    # private cache lookup below keeps imports on verified .py.
                    cached = entry.stat(follow_symlinks=False)
                    if (entry.name[:-1] not in expected_python
                            or not stat.S_ISREG(cached.st_mode)
                            or not 0 < cached.st_size < _GDR_MAX_UNUSED_BYTECODE_BYTES):
                        _gdr_refuse("unlisted or unsafe compiled project source")
                elif entry.name.endswith((".so", ".pyd")):
                    _gdr_refuse("unlisted compiled project source")
                if entry.name.endswith(".py"):
                    if not name and entry.name == "main.py":
                        visible = entry.stat(follow_symlinks=False)
                        if (not stat.S_ISREG(visible.st_mode)
                                or not 0 < visible.st_size < _GDR_MAX_PROJECT_FILE_BYTES):
                            _gdr_refuse("visible root source must be a bounded regular file")
                    observed_python.add(entry.name)
        if observed_python != expected_python:
            _gdr_refuse("missing or extra project Python file")
    contents = {}
    for name, size, digest in _GDR_EXPECTED_FILES:
        path = project_root / name
        try:
            raw = _gdr_read_regular(path, size)
        except RuntimeError as exc:
            # Evidence only: never normalize or accept mismatching source.
            # Read only a named bounded regular file through the same no-follow
            # guards; export identity metadata, not source or arbitrary paths.
            detail = "file=" + name + " expected_bytes=" + str(size)
            observed_digest = "unavailable"
            try:
                observed = path.lstat()
                regular = stat.S_ISREG(observed.st_mode)
                detail += (" observed_bytes=" + str(observed.st_size)
                           + " regular=" + str(regular)
                           + " symlink=" + str(stat.S_ISLNK(observed.st_mode)))
                if regular and 0 <= observed.st_size < _GDR_MAX_PROJECT_FILE_BYTES:
                    diagnostic = _gdr_read_regular(path, observed.st_size)
                    observed_digest = hashlib.sha256(diagnostic).hexdigest()
            except (OSError, RuntimeError):
                pass
            raise RuntimeError(str(exc) + " [" + detail + " sha256=" + observed_digest + "]") from exc
        if hashlib.sha256(raw).hexdigest() != digest:
            _gdr_refuse("project file differs from retained identity")
        contents[name] = raw
    return contents


def _gdr_assets(raw):
    try:
        tree = ast.parse(raw.decode("utf-8"), filename="gdr_assets.py")
    except (UnicodeError, SyntaxError, ValueError, RecursionError) as exc:
        raise RuntimeError("GDR project refused: invalid literal assets") from exc
    if len(tree.body) != 2:
        _gdr_refuse("assets require exactly two literal assignments")
    result = {}
    for node, (variable, filename, size, digest) in zip(tree.body, _GDR_EXPECTED_ASSETS):
        if (type(node) is not ast.Assign or len(node.targets) != 1
                or type(node.targets[0]) is not ast.Name or node.targets[0].id != variable
                or type(node.value) is not ast.Constant or type(node.value.value) is not str):
            _gdr_refuse("assets require named literal strings")
        content = node.value.value.encode("utf-8")
        if len(content) != size or hashlib.sha256(content).hexdigest() != digest:
            _gdr_refuse("asset differs from retained identity")
        result[filename] = content
    return result


def _gdr_prepare():
    _gdr_check_roots()
    root_file = Path(__file__).absolute()
    root_status = root_file.lstat()
    if (not stat.S_ISREG(root_status.st_mode)
            or not 0 < root_status.st_size < _GDR_MAX_PROJECT_FILE_BYTES):
        _gdr_refuse("root entrypoint must be a bounded regular file")
    project_root = root_file.parent
    contents = _gdr_inventory(project_root)
    assets = _gdr_assets(contents["gdr_assets.py"])
    temporary = tempfile.TemporaryDirectory(prefix="gdr-synthetic-data-")
    private = Path(temporary.name)
    try:
        for name, content in assets.items():
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(private / name, flags, 0o444)
            try:
                remaining = memoryview(content)
                while remaining:
                    written = os.write(descriptor, remaining)
                    if written <= 0:
                        _gdr_refuse("cannot materialize complete data asset")
                    remaining = remaining[written:]
            finally:
                os.close(descriptor)
            if _gdr_read_regular(private / name, len(content)) != content:
                _gdr_refuse("private data asset differs after write")
        _gdr_check_roots()
        # -B/dont_write_bytecode alone do not prevent stale cache reads. Route
        # cache lookup to an uncreated path in this fresh private data root.
        # Do not traverse platform caches or materialize executable source.
        sys.pycache_prefix = str(private / "unused-bytecode-cache")
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(project_root))
        return temporary, project_root, assets
    except BaseException:
        temporary.cleanup()
        raise


_GDR_RUNTIME_DIRECTORY, _GDR_PROJECT_ROOT, _GDR_ASSETS = _gdr_prepare()
import research.guidance_revision_drift.contracts as _gdr_contracts
import research.guidance_revision_drift.lean.main as _gdr_native
from research.guidance_revision_drift.lean.main import (
    GuidanceRevisionDriftAlgorithm as _NativeGuidanceRevisionDriftAlgorithm,
)
from research.guidance_revision_drift.lean_bridge import fixture_stream as _gdr_fixture_stream


def _gdr_bind():
    expected = {name: (size, digest) for name, size, digest in _GDR_EXPECTED_FILES}
    for name, module in tuple(sys.modules.items()):
        if name in {"data", "research"} or name.startswith(("data.", "research.")):
            filename = getattr(module, "__file__", None)
            path = name.replace(".", "/")
            member = path + "/__init__.py" if hasattr(module, "__path__") else path + ".py"
            if (member not in expected or type(filename) is not str
                    or Path(filename).absolute() != _GDR_PROJECT_ROOT / member
                    or Path(filename).resolve() != _GDR_PROJECT_ROOT / member):
                _gdr_refuse("native import origin differs from visible project source")
    # Recheck after imports; external custody binds the root's own bytes.
    _gdr_inventory(_GDR_PROJECT_ROOT)
    candidate = _gdr_contracts.Candidate.from_bytes(_GDR_ASSETS["gdr0a.draft.json"])
    if candidate.sha256 != __CANDIDATE_SHA256__:
        _gdr_refuse("immutable candidate semantics differ")
    if _gdr_fixture_stream() != _GDR_ASSETS["gdr-synthetic.jsonl"]:
        _gdr_refuse("invented fixture differs from native deterministic fixture")
    _gdr_contracts._SPEC_PATH = Path(_GDR_RUNTIME_DIRECTORY.name) / "gdr0a.draft.json"
    _gdr_native.DATA_PATH = Path(_GDR_RUNTIME_DIRECTORY.name) / "gdr-synthetic.jsonl"


_gdr_bind()


class GuidanceRevisionDriftAlgorithm(_NativeGuidanceRevisionDriftAlgorithm):
    """Root discovery class; native callbacks and economics are inherited."""
    _gdr_runtime_context = __RUNTIME_CONTEXT__


del _NativeGuidanceRevisionDriftAlgorithm
'''


def _file_manifest(files: dict[str, bytes]) -> dict[str, dict[str, object]]:
    return {name: {"bytes": len(raw), "sha256": hash_bytes(raw)}
            for name, raw in sorted(files.items())}


def _bounded_files(files: dict[str, bytes]) -> None:
    """Structural bounds only; exact closure is verified by reconstruction."""
    if type(files) is not dict or not 2 <= len(files) <= MAX_PROJECT_FILES - RESERVED_PROJECT_FILES:
        raise QCProjectError("exact bounded project-file dictionary required")
    if ("main.py" not in files
            or any(type(name) is not str or len(name) > 256 or not _PYTHON_PATH.fullmatch(name)
                   or type(raw) is not bytes or not len(raw) < MAX_PROJECT_FILE_BYTES
                   or (not raw and name.rsplit("/", 1)[-1] != "__init__.py")
                   for name, raw in files.items())
            or len({name.casefold() for name in files}) != len(files)):
        raise QCProjectError("project requires safe bounded readable Python files")


def _literal_assets(candidate: bytes, fixture: bytes) -> bytes:
    values = (("_GDR_CANDIDATE_JSON", candidate), ("_GDR_FIXTURE_JSONL", fixture))
    parts = []
    for name, raw in values:
        text = raw.decode("utf-8")
        if '"""' in text:
            raise QCProjectError("asset contains raw literal delimiter")
        parts.append(name + ' = r"""' + text + '"""\n')
    source = "".join(parts).encode("utf-8")
    tree = ast.parse(source)
    if (len(tree.body) != 2 or any(type(node.value) is not ast.Constant
            or node.value.value.encode("utf-8") != raw
            for node, (_, raw) in zip(tree.body, values))):
        raise QCProjectError("transparent asset literals do not preserve exact bytes")
    return source


def _prepare_project() -> tuple[dict[str, bytes], dict]:
    full_review_source = source_manifest()
    try:
        raw = build_native_bundle()
        bundle_sha256 = hash_bytes(raw)
        bundle = verify_native_bundle(raw, expected_sha256=bundle_sha256)
    except BundleError as exc:
        raise QCProjectError("cannot prepare current-source readable project") from exc
    with ZipFile(BytesIO(raw), "r", allowZip64=False) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    files = {name: content for name, content in members.items() if name.endswith(".py")}
    files[ASSET_PATH] = _literal_assets(members[_CANDIDATE_PATH], members[SIDECAR_PATH])
    expected_files = tuple((name, len(content), hash_bytes(content))
                           for name, content in sorted(files.items()))
    expected_assets = tuple((variable, filename, len(members[path]), hash_bytes(members[path]))
        for variable, filename, path in (
            ("_GDR_CANDIDATE_JSON", "gdr0a.draft.json", _CANDIDATE_PATH),
            ("_GDR_FIXTURE_JSONL", "gdr-synthetic.jsonl", SIDECAR_PATH)))
    body = bundle["manifest"]
    runtime_context = {"runtime_source_sha256": body["source_manifest_sha256"],
        "bundle_sha256": bundle_sha256, "candidate_sha256": body["candidate_sha256"],
        "fixture_sha256": body["members"][SIDECAR_PATH]["sha256"]}
    root_source = _ROOT_TEMPLATE
    for token, value in (("__FILES__", repr(expected_files)),
                         ("__ASSETS__", repr(expected_assets)),
                         ("__CANDIDATE_SHA256__", repr(body["candidate_sha256"])),
                         ("__RUNTIME_CONTEXT__", repr(runtime_context))):
        if root_source.count(token) != 1:
            raise QCProjectError("invalid fixed readable root template")
        root_source = root_source.replace(token, value)
    files["main.py"] = root_source.encode("ascii")
    _bounded_files(files)
    inventory = _file_manifest(files)
    fixture = body["members"][SIDECAR_PATH]
    manifest = {
        "schema": "gdr.synthetic.python-project.v3",
        "purpose": "offline_readable_project_preparation_not_native_certification",
        "format": "visible_native_Python_and_plain_raw_JSON_JSONL_literals",
        "entrypoint": "main.py",
        "native_entrypoint": body["entrypoint"],
        "project_sha256": hash_payload(inventory),
        "project_files": inventory,
        "bundle_sha256": bundle_sha256,
        "bundle_bytes": len(raw),
        "bundle_role": "offline_native_closure_audit_reference_not_uploaded_archive",
        "bundle_manifest_member": MANIFEST_PATH,
        "source_manifest_sha256": hash_payload(full_review_source),
        "runtime_source_sha256": body["source_manifest_sha256"],
        "runtime_context": runtime_context,
        "reserved_project_files": RESERVED_PROJECT_FILES,
        "project_files_with_reserved_notebook": len(files) + RESERVED_PROJECT_FILES,
        "candidate_sha256": body["candidate_sha256"],
        "candidate_file_sha256": hash_bytes(members[_CANDIDATE_PATH]),
        "fixture_sha256": fixture["sha256"],
        "fixture_bytes": fixture["bytes"],
        "fixture_frames": 372,
        "runtime_materialization": "two_plain_data_files_only_in_private_temporary_directory",
        "source_materialized": False,
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
        verify_native_bundle(raw, expected_sha256=bundle_sha256)
        if source_manifest() != full_review_source:
            raise BundleError("full review source changed during readable project preparation")
    except BundleError as exc:
        raise QCProjectError("source changed while preparing readable project") from exc
    return files, manifest


def build_qc_project() -> dict[str, bytes]:
    """Detached deterministic readable files; no write/upload/run."""
    return dict(_prepare_project()[0])


def qc_project_manifest() -> dict:
    """Fresh source/candidate/fixture identities, never approval."""
    return _prepare_project()[1]


def verify_qc_project(files: dict[str, bytes], *, expected_sha256: str) -> dict:
    """Require the external map anchor and exact current-source reconstruction."""
    if type(files) is not dict or not 2 <= len(files) <= MAX_PROJECT_FILES:
        raise QCProjectError("exact bounded project-file dictionary required")
    snapshot = files.copy()
    _bounded_files(snapshot)
    if (type(expected_sha256) is not str or not _DIGEST.fullmatch(expected_sha256)
            or hash_payload(_file_manifest(snapshot)) != expected_sha256):
        raise QCProjectError("project differs from caller-retained file-map anchor")
    expected_files, manifest = _prepare_project()
    if snapshot != expected_files:
        raise QCProjectError("project does not reconstruct from exact current source")
    return {"status": "verified_offline_content_only", **manifest}
