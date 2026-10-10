"""Exact native import closure, separate from the full offline review bundle.

Preparation only: no SDK import, extraction, execution, upload or permission.
Offline-only helper/review changes do not alter these executable payload bytes.
The enclosing project preparation separately retains the full review identity.
"""
from __future__ import annotations

import ast
from io import BytesIO
from pathlib import Path
import sys
from zipfile import BadZipFile, ZIP_STORED, ZipFile

from data.hashing import canonical_json, hash_bytes, hash_payload
from research.guidance_revision_drift.bundle import (
    BundleError, MANIFEST_PATH, SIDECAR_PATH, _archive, _CANDIDATE_PATH,
    _DATE, _FILE_MODE,
)
from research.guidance_revision_drift.contracts import (
    Candidate, CandidateError, MAX_SOURCE_DOCUMENT_BYTES, _read_regular_file,
)
from research.guidance_revision_drift.lean_bridge import fixture_stream
from research.guidance_revision_drift.reporting import source_manifest


ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = "research/guidance_revision_drift/lean/main.py"
MAX_NATIVE_BUNDLE_BYTES = 360_000
NATIVE_MODULES = frozenset({
    "data.hashing", "data.financial_primitives",
    "research.guidance_revision_drift.lean.main",
    "research.guidance_revision_drift.lean_bridge",
    "research.guidance_revision_drift.assessment",
    "research.guidance_revision_drift.fixtures",
    "research.guidance_revision_drift.simulation",
    "research.guidance_revision_drift.timing",
    "research.guidance_revision_drift.events",
    "research.guidance_revision_drift.universe",
    "research.guidance_revision_drift.archive",
    "research.guidance_revision_drift.formulas",
    "research.guidance_revision_drift.contracts",
    "research.guidance_revision_drift.native_observation",
    "research.guidance_revision_drift.trace_transport",
})
INITIALIZERS = frozenset({"data/__init__.py", "research/__init__.py",
    "research/guidance_revision_drift/__init__.py",
    "research/guidance_revision_drift/lean/__init__.py"})
SOURCE_PATHS = frozenset(name.replace(".", "/") + ".py" for name in NATIVE_MODULES) | INITIALIZERS | {_CANDIDATE_PATH}


def _import_closure(members):
    """Check every syntactic edge, including deferred/conditional imports.

    Dynamic imports/evaluation and relative imports refuse. A reviewed explicit
    closure must equal the actual entrypoint graph; no arbitrary lane discovery.
    """
    pending = [ENTRYPOINT] + sorted(INITIALIZERS)
    visited = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        try:
            tree = ast.parse(members[path], filename=path)
        except (SyntaxError, KeyError, ValueError, RecursionError) as exc:
            raise BundleError("invalid or missing native closure source") from exc
        for node in ast.walk(tree):
            # Refuse dynamic-loader imports even when their call name is
            # aliased. This is a guard over this exact reviewed source graph,
            # not a general proof that arbitrary Python is non-executable.
            if (isinstance(node, ast.Name)
                    and node.id in {"__import__", "eval", "exec", "__builtins__"}):
                raise BundleError("dynamic execution reference outside native closure")
            if isinstance(node, ast.Call):
                called = node.func.id if isinstance(node.func, ast.Name) else (
                    node.func.attr if isinstance(node.func, ast.Attribute) else None)
                if called in {"__import__", "import_module", "eval", "exec"}:
                    raise BundleError("dynamic execution/import outside native closure")
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    raise BundleError("relative native import needs a reviewed resolver")
                names = [node.module]
            else:
                continue
            for name in names:
                if name.split(".")[0] in {"importlib", "builtins", "runpy"}:
                    raise BundleError("dynamic loader dependency outside native closure")
                if name == "AlgorithmImports" and path == ENTRYPOINT:
                    continue
                if name == "__future__" or name.split(".")[0] in sys.stdlib_module_names:
                    continue
                if name not in NATIVE_MODULES:
                    raise BundleError("unreviewed native dependency: " + str(name))
                pending.append(name.replace(".", "/") + ".py")
    expected = SOURCE_PATHS - {_CANDIDATE_PATH}
    if visited != expected:
        raise BundleError("native imports differ from the exact reviewed closure")


def _snapshot():
    try:
        full_review = source_manifest()
        members = {name: _read_regular_file(ROOT / name, MAX_SOURCE_DOCUMENT_BYTES)
                   for name in sorted(SOURCE_PATHS)}
        if any(hash_bytes(raw) != full_review.get(name) for name, raw in members.items()):
            raise BundleError("native source changed while preparing closure")
        _import_closure(members)
        candidate = Candidate.from_bytes(members[_CANDIDATE_PATH])
        runtime_source = {name: hash_bytes(raw) for name, raw in sorted(members.items())}
        members[SIDECAR_PATH] = fixture_stream()
        manifest = {
            "schema": "gdr.synthetic.native-closure.v1",
            "purpose": "offline_native_closure_preparation_not_runtime_certification",
            "entrypoint": ENTRYPOINT,
            "source_manifest": runtime_source,
            "source_manifest_sha256": hash_payload(runtime_source),
            "candidate_sha256": candidate.sha256,
            "members": {name: {"bytes": len(raw), "sha256": hash_bytes(raw)}
                        for name, raw in sorted(members.items())},
            "SDK_included": False, "native_runtime_verified": False,
            "qc_upload_allowed": False, "qc_launch_allowed": False,
            "market_evidence": False,
        }
        members[MANIFEST_PATH] = canonical_json(manifest).encode("utf-8")
        if source_manifest() != full_review:
            raise BundleError("review source epoch changed during native preparation")
        return members, manifest
    except (CandidateError, OSError) as exc:
        raise BundleError("cannot prepare bounded native closure") from exc


def build_native_bundle():
    raw = _archive(_snapshot()[0])
    if len(raw) > MAX_NATIVE_BUNDLE_BYTES:
        raise BundleError("native closure exceeds conservative carrier capacity")
    return raw


def verify_native_bundle(raw, *, expected_sha256):
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_NATIVE_BUNDLE_BYTES
            or type(expected_sha256) is not str or len(expected_sha256) != 64
            or any(c not in "0123456789abcdef" for c in expected_sha256)
            or hash_bytes(raw) != expected_sha256):
        raise BundleError("native closure differs from retained bounded anchor")
    expected, manifest = _snapshot()
    try:
        with ZipFile(BytesIO(raw), allowZip64=False) as archive:
            infos = archive.infolist()
            if (archive.comment or [i.filename for i in infos] != sorted(expected)
                    or any(i.compress_type != ZIP_STORED or i.file_size != len(expected[i.filename])
                        or i.compress_size != i.file_size or i.date_time != _DATE
                        or i.create_system != 3 or i.external_attr != _FILE_MODE
                        or i.extra or i.comment or i.flag_bits or i.internal_attr for i in infos)):
                raise BundleError("noncanonical or incomplete native archive")
            if any(archive.read(i) != expected[i.filename] for i in infos):
                raise BundleError("native archive differs from current runtime bytes")
        if _archive(expected) != raw:
            raise BundleError("noncanonical native archive encoding")
    except (BadZipFile, OSError, ValueError, RuntimeError, EOFError) as exc:
        if isinstance(exc, BundleError):
            raise
        raise BundleError("invalid native closure archive") from exc
    return {"status": "verified_offline_content_only", "manifest": manifest,
            "sha256": expected_sha256, "bytes": len(raw)}
