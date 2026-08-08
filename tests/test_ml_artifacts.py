"""Tests for ml/artifacts.py -- strategy doc 5.4/5.5: atomic writes,
artifact-hash-mismatch refusal, and manifest identity checks."""
from __future__ import annotations

import os
import threading

import pytest

import ml.artifacts as artifacts_module
import ml.immutable_io as immutable_io_module
from assistant.schemas import EvidenceStatus
from ml.artifacts import (
    ArtifactError,
    load_model_artifact,
    load_model_manifest,
    save_model_artifact,
    save_model_manifest,
)
from ml.contracts import ModelManifest
from ml.hashing import hash_bytes


_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64


def _manifest(**overrides) -> ModelManifest:
    kwargs = dict(
        model_id="model-1",
        model_version="0.1.0",
        task="volatility_forecast",
        created_at="2026-07-31T00:00:00+00:00",
        dataset_id="ds-1",
        dataset_hash=_HASH_A,
        feature_set_version="fs-1",
        ordered_feature_names=("realized_vol_20d",),
        label_version="lv-1",
        algorithm="ewma_baseline",
        hyperparameters={"halflife": 20},
        random_seed=42,
        training_window={"start": "2020-01-01", "end": "2025-01-01"},
        validation_windows=({"start": "2025-01-01", "end": "2025-06-01"},),
        dependency_versions={"scikit-learn": "1.9.0"},
        artifact_hash=_HASH_B,
        evaluation_report_hash=_HASH_C,
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
    manifest = _manifest(artifact_hash="0" * 64)

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


def test_artifact_paths_cannot_escape_the_supplied_directory(tmp_path):
    with pytest.raises(ArtifactError, match="plain relative file name"):
        save_model_artifact({"a": 1}, directory=tmp_path, filename="../escape.joblib")
    with pytest.raises(ArtifactError, match="plain relative file name"):
        load_model_manifest(
            directory=tmp_path,
            filename="subdir\\manifest.json",
            model_id="model-1",
            model_version="0.1.0",
        )


def test_versioned_artifact_path_is_immutable(tmp_path):
    save_model_artifact({"a": 1}, directory=tmp_path, filename="model.joblib")
    with pytest.raises(ArtifactError, match="refusing to overwrite"):
        save_model_artifact({"a": 2}, directory=tmp_path, filename="model.joblib")


def test_idempotent_rewrite_of_identical_artifact_is_allowed(tmp_path):
    first = save_model_artifact({"a": 1}, directory=tmp_path, filename="model.joblib")
    second = save_model_artifact({"a": 1}, directory=tmp_path, filename="model.joblib")
    assert first == second


def test_load_manifest_can_verify_its_external_hash(tmp_path):
    manifest = _manifest()
    save_model_manifest(manifest, directory=tmp_path, filename="manifest.json")
    expected = hash_bytes((tmp_path / "manifest.json").read_bytes())
    restored = load_model_manifest(
        directory=tmp_path,
        filename="manifest.json",
        model_id="model-1",
        model_version="0.1.0",
        expected_manifest_hash=expected,
    )
    assert restored == manifest

    with pytest.raises(ArtifactError, match="manifest hash mismatch"):
        load_model_manifest(
            directory=tmp_path,
            filename="manifest.json",
            model_id="model-1",
            model_version="0.1.0",
            expected_manifest_hash="0" * 64,
        )


@pytest.mark.parametrize("kind", ["artifact", "manifest"])
def test_conflicting_concurrent_immutable_writers_have_one_winner(
    tmp_path, monkeypatch, kind
):
    both_reached_publish = threading.Barrier(2)
    real_replace = os.replace

    def synchronized_replace(source, destination):
        both_reached_publish.wait(timeout=5)
        return real_replace(source, destination)

    monkeypatch.setattr(artifacts_module.os, "replace", synchronized_replace)
    if kind == "artifact":
        writers = [
            lambda value=value: save_model_artifact(
                {"writer": value}, directory=tmp_path, filename="shared.joblib"
            )
            for value in (1, 2)
        ]
    else:
        writers = [
            lambda manifest=manifest: save_model_manifest(
                manifest, directory=tmp_path, filename="shared.json"
            )
            for manifest in (
                _manifest(random_seed=1),
                _manifest(random_seed=2),
            )
        ]
    outcomes = []
    outcome_lock = threading.Lock()

    def run(writer):
        try:
            writer()
            outcome = "saved"
        except ArtifactError:
            outcome = "conflict"
        with outcome_lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=run, args=(writer,)) for writer in writers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(outcomes) == ["conflict", "saved"]
    assert not list(tmp_path.glob("*.tmp"))


def test_identical_concurrent_artifact_writers_are_idempotent(tmp_path):
    start = threading.Barrier(2)
    outcomes = []

    def write():
        start.wait(timeout=5)
        outcomes.append(
            save_model_artifact(
                {"same": [1, 2]}, directory=tmp_path, filename="shared.joblib"
            )
        )

    threads = [threading.Thread(target=write) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert len(outcomes) == 2
    assert outcomes[0] == outcomes[1]
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("kind", ["artifact", "manifest"])
def test_interrupted_immutable_publish_leaves_no_destination_or_temp(
    tmp_path, monkeypatch, kind
):
    def fail_publish(_source, _destination):
        raise OSError("injected publish interruption")

    monkeypatch.setattr(immutable_io_module.os, "link", fail_publish)
    if kind == "artifact":
        write = lambda: save_model_artifact(
            {"a": 1}, directory=tmp_path, filename="interrupted.joblib"
        )
        destination = tmp_path / "interrupted.joblib"
    else:
        write = lambda: save_model_manifest(
            _manifest(), directory=tmp_path, filename="interrupted.json"
        )
        destination = tmp_path / "interrupted.json"

    with pytest.raises(OSError, match="injected publish interruption"):
        write()

    assert not destination.exists()
    assert not list(tmp_path.glob("*.tmp"))
