"""Tests for ml/artifacts.py -- strategy doc 5.4/5.5: atomic writes,
artifact-hash-mismatch refusal, and manifest identity checks."""
from __future__ import annotations

import pytest

from assistant.schemas import EvidenceStatus
from ml.artifacts import (
    ArtifactError,
    load_model_artifact,
    load_model_manifest,
    save_model_artifact,
    save_model_manifest,
)
from ml.contracts import ModelManifest


def _manifest(**overrides) -> ModelManifest:
    kwargs = dict(
        model_id="model-1",
        model_version="0.1.0",
        task="volatility_forecast",
        created_at="2026-07-31T00:00:00+00:00",
        dataset_id="ds-1",
        dataset_hash="def456",
        feature_set_version="fs-1",
        ordered_feature_names=("realized_vol_20d",),
        label_version="lv-1",
        algorithm="ewma_baseline",
        hyperparameters={"halflife": 20},
        random_seed=42,
        training_window={"start": "2020-01-01", "end": "2025-01-01"},
        validation_windows=({"start": "2025-01-01", "end": "2025-06-01"},),
        dependency_versions={"scikit-learn": "1.9.0"},
        artifact_hash="placeholder",
        evaluation_report_hash="reporthash",
        evidence_status=EvidenceStatus.EXPLORATORY,
    )
    kwargs.update(overrides)
    return ModelManifest(**kwargs)


def test_save_and_load_model_artifact_round_trips(tmp_path):
    obj = {"weights": [1.0, 2.0, 3.0]}
    artifact_hash = save_model_artifact(obj, directory=tmp_path, filename="model.joblib")
    manifest = _manifest(artifact_hash=artifact_hash)

    loaded = load_model_artifact(manifest, directory=tmp_path, filename="model.joblib")

    assert loaded == obj
    assert (tmp_path / "model.joblib").exists()
    assert not list(tmp_path.glob("*.tmp"))  # no leftover temp file


def test_save_model_artifact_is_atomic_no_partial_file_on_disk(tmp_path):
    save_model_artifact({"a": 1}, directory=tmp_path, filename="model.joblib")
    entries = list(tmp_path.iterdir())
    assert entries == [tmp_path / "model.joblib"]


def test_load_model_artifact_refuses_hash_mismatch(tmp_path):
    save_model_artifact({"weights": [1.0]}, directory=tmp_path, filename="model.joblib")
    manifest = _manifest(artifact_hash="not-the-real-hash")

    with pytest.raises(ArtifactError, match="hash mismatch"):
        load_model_artifact(manifest, directory=tmp_path, filename="model.joblib")


def test_load_model_artifact_refuses_tampered_file(tmp_path):
    artifact_hash = save_model_artifact({"weights": [1.0]}, directory=tmp_path, filename="model.joblib")
    manifest = _manifest(artifact_hash=artifact_hash)
    (tmp_path / "model.joblib").write_bytes(b"tampered bytes")

    with pytest.raises(ArtifactError, match="hash mismatch"):
        load_model_artifact(manifest, directory=tmp_path, filename="model.joblib")


def test_save_and_load_model_manifest_round_trips(tmp_path):
    artifact_hash = save_model_artifact({"a": 1}, directory=tmp_path, filename="model.joblib")
    manifest = _manifest(artifact_hash=artifact_hash)
    save_model_manifest(manifest, directory=tmp_path, filename="manifest.json")

    restored = load_model_manifest(
        directory=tmp_path,
        filename="manifest.json",
        model_id="model-1",
        model_version="0.1.0",
    )

    assert restored == manifest


def test_load_model_manifest_refuses_model_id_mismatch(tmp_path):
    manifest = _manifest()
    save_model_manifest(manifest, directory=tmp_path, filename="manifest.json")

    with pytest.raises(ArtifactError, match="expected"):
        load_model_manifest(
            directory=tmp_path,
            filename="manifest.json",
            model_id="a-different-model",
            model_version="0.1.0",
        )


def test_load_model_manifest_refuses_model_version_mismatch(tmp_path):
    manifest = _manifest()
    save_model_manifest(manifest, directory=tmp_path, filename="manifest.json")

    with pytest.raises(ArtifactError, match="expected"):
        load_model_manifest(
            directory=tmp_path,
            filename="manifest.json",
            model_id="model-1",
            model_version="9.9.9",
        )
