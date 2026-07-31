"""Atomic, hash-verified artifact storage for ML models (strategy doc 5.4).

Artifacts are joblib-serialized and therefore code-execution-capable on
load, exactly like any pickle-based format. `load_model_artifact()` is
deliberately the only sanctioned way to load one in this package: it
requires an already-constructed (and therefore already __post_init__-
validated) ModelManifest and re-verifies the artifact's sha256 hash on raw
bytes BEFORE deserializing -- a tampered or wrong file is rejected as
bytes, never handed to joblib.load(). Never load a joblib file from this
application's artifact directory by any other path, and never point this
at a directory outside the application's own control.
"""
from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import joblib

from ml.contracts import ModelManifest
from ml.hashing import canonical_json, hash_bytes


class ArtifactError(ValueError):
    """An artifact write or load failed its integrity/identity check."""


def _atomic_write_bytes(directory: Path, filename: str, data: bytes) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=f".{filename}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, directory / filename)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def save_model_artifact(model: Any, *, directory: Path, filename: str) -> str:
    """Atomically serialize `model` with joblib and return the sha256 hex
    digest computed over the written bytes (strategy doc 5.4 steps 1-4)."""
    buffer = io.BytesIO()
    joblib.dump(model, buffer)
    data = buffer.getvalue()
    _atomic_write_bytes(Path(directory), filename, data)
    return hash_bytes(data)


def save_model_manifest(manifest: ModelManifest, *, directory: Path, filename: str) -> str:
    """Atomically write a ModelManifest as canonical JSON; returns the
    payload's own sha256 hash (5.4 step 5) -- distinct from
    `manifest.artifact_hash`, which is the hash of the model artifact this
    manifest describes."""
    data = canonical_json(manifest.to_dict()).encode("utf-8")
    _atomic_write_bytes(Path(directory), filename, data)
    return hash_bytes(data)


def load_model_artifact(manifest: ModelManifest, *, directory: Path, filename: str) -> Any:
    """Load a joblib model artifact, verifying its sha256 hash against
    `manifest.artifact_hash` before deserializing (5.4 step 6)."""
    path = Path(directory) / filename
    data = path.read_bytes()
    actual_hash = hash_bytes(data)
    if actual_hash != manifest.artifact_hash:
        raise ArtifactError(
            f"artifact hash mismatch loading {path}: manifest declares "
            f"{manifest.artifact_hash}, file hashes to {actual_hash}"
        )
    return joblib.load(io.BytesIO(data))


def load_model_manifest(
    *, directory: Path, filename: str, model_id: str, model_version: str
) -> ModelManifest:
    """Read and reconstruct a ModelManifest, requiring it to declare the
    caller's expected model_id/model_version -- callers must not silently
    load a manifest for a different model than the one they asked for."""
    path = Path(directory) / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("model_id") != model_id or payload.get("model_version") != model_version:
        raise ArtifactError(
            f"manifest at {path} declares model_id={payload.get('model_id')!r} "
            f"model_version={payload.get('model_version')!r}, expected "
            f"{model_id!r}/{model_version!r}"
        )
    return ModelManifest.from_dict(payload)
