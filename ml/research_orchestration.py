"""Review-gated, content-addressed research orchestration for ML-FS-6.

This layer does not fetch data, select a favorable result, update a registry,
or create trading state.  It only admits already-built authoritative datasets,
verifies human review of frozen specs, and binds a distinct untouched
confirmation dataset to a verified discovery result.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from ml.contracts import DatasetManifest
from ml.datasets import load_dataset
from ml.experiment_contracts import (
    ConfirmationSpec,
    ExperimentRunRecord,
    ExperimentSpec,
)
from ml.experiments import run_experiment
from ml.hashing import canonical_json, hash_bytes, hash_payload
from ml.immutable_io import (
    ImmutableFileConflictError,
    exclusive_file_lock,
    publish_immutable_bytes,
)

ORCHESTRATION_SCHEMA_VERSION = "1"


class ResearchOrchestrationError(ValueError):
    """A dataset, review, or discovery/confirmation transition is invalid."""


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ResearchOrchestrationError(f"{name} must be a non-empty trimmed string")
    return value


def _timestamp(value: Any, name: str) -> str:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResearchOrchestrationError(f"{name} must be timezone-aware ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ResearchOrchestrationError(f"{name} must be timezone-aware ISO-8601")
    return parsed.isoformat()


def _sha256(value: Any, name: str) -> str:
    text = _text(value, name)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ResearchOrchestrationError(f"{name} must be a lowercase SHA-256 digest")
    return text


def _read_json(path: Path, name: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchOrchestrationError(f"could not read {name} {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ResearchOrchestrationError(f"{name} must contain one JSON object")
    return payload


def _write_immutable_json(path: Path, payload: Mapping[str, Any]) -> bool:
    data = canonical_json(dict(payload)).encode("utf-8")
    try:
        return publish_immutable_bytes(Path(path), data)
    except ImmutableFileConflictError as exc:
        raise ResearchOrchestrationError(
            f"refusing to overwrite immutable artifact {path}"
        ) from exc


def _write_immutable_bytes(path: Path, data: bytes) -> bool:
    try:
        return publish_immutable_bytes(Path(path), data)
    except ImmutableFileConflictError as exc:
        raise ResearchOrchestrationError(
            f"refusing to overwrite immutable artifact {path}"
        ) from exc


@dataclasses.dataclass(frozen=True)
class SpecReviewAttestation:
    spec_hash: str
    reviewer: str
    reviewed_at: str
    decision: str
    review_scope: str
    notes: str
    schema_version: str = ORCHESTRATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ORCHESTRATION_SCHEMA_VERSION:
            raise ResearchOrchestrationError("unsupported review schema_version")
        _sha256(self.spec_hash, "spec_hash")
        _text(self.reviewer, "reviewer")
        object.__setattr__(self, "reviewed_at", _timestamp(self.reviewed_at, "reviewed_at"))
        if self.decision != "approved":
            raise ResearchOrchestrationError(
                "spec review decision must be 'approved' before an experiment may run"
            )
        if self.review_scope != "research_behavior_and_gates":
            raise ResearchOrchestrationError(
                "review_scope must be 'research_behavior_and_gates'"
            )
        _text(self.notes, "notes")

    @property
    def review_hash(self) -> str:
        return hash_payload(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SpecReviewAttestation":
        fields = {field.name for field in dataclasses.fields(cls)}
        if not isinstance(payload, Mapping) or set(payload) != fields:
            raise ResearchOrchestrationError(
                f"review keys must be exactly {sorted(fields)}"
            )
        try:
            return cls(**dict(payload))
        except TypeError as exc:
            raise ResearchOrchestrationError(f"invalid review attestation: {exc}") from exc


def load_reviewed_spec(spec_path: Path, review_path: Path) -> tuple[ExperimentSpec, SpecReviewAttestation]:
    spec = ExperimentSpec.from_dict(_read_json(spec_path, "experiment spec"))
    review = SpecReviewAttestation.from_dict(_read_json(review_path, "spec review"))
    if review.spec_hash != spec.spec_hash:
        raise ResearchOrchestrationError(
            "spec review hash does not match the loaded immutable experiment spec"
        )
    return spec, review


@dataclasses.dataclass(frozen=True)
class ContentAddressedDataset:
    dataset_id: str
    dataset_hash: str
    manifest_hash: str
    directory: str
    point_in_time_data: bool
    schema_version: str = ORCHESTRATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ORCHESTRATION_SCHEMA_VERSION:
            raise ResearchOrchestrationError("unsupported dataset address schema_version")
        _text(self.dataset_id, "dataset_id")
        _sha256(self.dataset_hash, "dataset_hash")
        _sha256(self.manifest_hash, "manifest_hash")
        _text(self.directory, "directory")
        if self.point_in_time_data is not True:
            raise ResearchOrchestrationError(
                "research campaign datasets must derive point_in_time_data=true"
            )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def materialize_content_addressed_dataset(
    source_directory: Path,
    dataset_id: str,
    store_root: Path,
) -> ContentAddressedDataset:
    """Verify and copy one dataset into ``store_root/<dataset_hash>``."""
    features, labels, manifest = load_dataset(source_directory, dataset_id)
    if not manifest.point_in_time_data:
        raise ResearchOrchestrationError(
            "only a coverage-derived point_in_time_data=true dataset may enter the "
            "authoritative research store"
        )
    if not {"availability", "universe"} <= set(manifest.input_hashes):
        raise ResearchOrchestrationError(
            "authoritative dataset must include availability and universe sidecars"
        )
    destination = Path(store_root) / manifest.dataset_hash
    del features, labels
    filenames = (
        f"{dataset_id}.features.csv.gz",
        f"{dataset_id}.labels.csv.gz",
        f"{dataset_id}.availability.csv.gz",
        f"{dataset_id}.universe.csv.gz",
        f"{dataset_id}.manifest.json",
    )
    lock_path = destination / ".research-dataset.lock"
    with exclusive_file_lock(lock_path):
        created: list[Path] = []
        try:
            for filename in filenames:
                source = Path(source_directory) / filename
                try:
                    data = source.read_bytes()
                except OSError as exc:
                    raise ResearchOrchestrationError(
                        f"authoritative dataset artifact is missing: {source}"
                    ) from exc
                target = destination / filename
                if _write_immutable_bytes(target, data):
                    created.append(target)
            _, _, verified = load_dataset(destination, dataset_id)
            if verified != manifest:
                raise ResearchOrchestrationError(
                    "content-addressed dataset replay changed its manifest"
                )
            address = ContentAddressedDataset(
                dataset_id=dataset_id,
                dataset_hash=manifest.dataset_hash,
                manifest_hash=hash_payload(manifest.to_dict()),
                directory=manifest.dataset_hash,
                point_in_time_data=True,
            )
            address_path = destination / "content-address.json"
            if _write_immutable_json(address_path, address.to_dict()):
                created.append(address_path)
        except BaseException:
            for path in reversed(created):
                path.unlink(missing_ok=True)
            raise
    return address


def load_content_addressed_dataset(
    directory: Path, dataset_id: str
) -> tuple[DatasetManifest, ContentAddressedDataset]:
    _, _, manifest = load_dataset(directory, dataset_id)
    address = ContentAddressedDataset(
        **_read_json(Path(directory) / "content-address.json", "dataset address")
    )
    if (
        Path(directory).name != manifest.dataset_hash
        or address.dataset_hash != manifest.dataset_hash
        or address.dataset_id != dataset_id
        or address.manifest_hash != hash_payload(manifest.to_dict())
        or address.directory != Path(directory).name
    ):
        raise ResearchOrchestrationError(
            "dataset directory/address/manifest content identity does not agree"
        )
    return manifest, address


@dataclasses.dataclass(frozen=True)
class ConfirmationRequest:
    discovery_experiment_id: str
    discovery_spec_hash: str
    discovery_report_hash: str
    discovery_run_hash: str
    discovery_dataset_hash: str
    confirmation_experiment_id: str
    confirmation_spec_hash: str
    confirmation_dataset_id: str
    confirmation_dataset_hash: str
    requested_at: str
    review_status: str = "review_required"
    schema_version: str = ORCHESTRATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ORCHESTRATION_SCHEMA_VERSION:
            raise ResearchOrchestrationError("unsupported confirmation request schema_version")
        for name in (
            "discovery_experiment_id", "confirmation_experiment_id", "confirmation_dataset_id"
        ):
            _text(getattr(self, name), name)
        for name in (
            "discovery_spec_hash", "discovery_report_hash", "discovery_run_hash",
            "discovery_dataset_hash", "confirmation_spec_hash", "confirmation_dataset_hash",
        ):
            _sha256(getattr(self, name), name)
        if self.discovery_experiment_id == self.confirmation_experiment_id:
            raise ResearchOrchestrationError("confirmation must use a distinct experiment_id")
        if self.discovery_dataset_hash == self.confirmation_dataset_hash:
            raise ResearchOrchestrationError(
                "confirmation must use a distinct untouched dataset hash"
            )
        object.__setattr__(self, "requested_at", _timestamp(self.requested_at, "requested_at"))
        if self.review_status != "review_required":
            raise ResearchOrchestrationError(
                "a generated confirmation request must remain review_required"
            )

    @property
    def request_hash(self) -> str:
        return hash_payload(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ConfirmationRequest":
        fields = {field.name for field in dataclasses.fields(cls)}
        if not isinstance(payload, Mapping) or set(payload) != fields:
            raise ResearchOrchestrationError(
                f"confirmation request keys must be exactly {sorted(fields)}"
            )
        return cls(**dict(payload))


def _load_discovery_evidence(
    output_directory: Path, experiment_id: str
) -> tuple[ExperimentSpec, ExperimentRunRecord, bytes]:
    output = Path(output_directory)
    spec = ExperimentSpec.from_dict(
        _read_json(output / f"{experiment_id}.spec.json", "discovery spec")
    )
    run_payload = _read_json(output / f"{experiment_id}.run.json", "discovery run")
    run = ExperimentRunRecord.from_dict(run_payload)
    report_path = output / f"{experiment_id}.report.json"
    try:
        report_bytes = report_path.read_bytes()
        report = json.loads(report_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchOrchestrationError(f"could not read discovery report: {exc}") from exc
    if (
        spec.mode != "discovery"
        or spec.experiment_id != experiment_id
        or run.identity.spec_hash != spec.spec_hash
        or run.report_hash != hash_bytes(report_bytes)
        or run.verdict != "confirmation_run_requested"
        or not isinstance(report, Mapping)
        or report.get("verdict") != "confirmation_run_requested"
    ):
        raise ResearchOrchestrationError(
            "discovery evidence does not contain a verified confirmation request"
        )
    return spec, run, report_bytes


def prepare_confirmation_request(
    *,
    discovery_output_directory: Path,
    discovery_experiment_id: str,
    confirmation_dataset_directory: Path,
    confirmation_dataset_id: str,
    confirmation_experiment_id: str,
    created_at: str,
    spec_output_path: Path,
    request_output_path: Path,
) -> tuple[ExperimentSpec, ConfirmationRequest]:
    discovery, discovery_run, report_bytes = _load_discovery_evidence(
        discovery_output_directory, discovery_experiment_id
    )
    confirmation_manifest, _ = load_content_addressed_dataset(
        confirmation_dataset_directory, confirmation_dataset_id
    )
    if confirmation_manifest.task != discovery.task:
        raise ResearchOrchestrationError("confirmation dataset task differs from discovery")
    if confirmation_manifest.dataset_hash == discovery_run.dataset_hash:
        raise ResearchOrchestrationError(
            "confirmation dataset is not untouched: it has the discovery dataset hash"
        )
    payload = discovery.to_dict()
    payload.update(
        experiment_id=confirmation_experiment_id,
        mode="confirmation",
        created_at=_timestamp(created_at, "created_at"),
        confirmation=ConfirmationSpec(
            parent_experiment_id=discovery.experiment_id,
            parent_spec_hash=discovery.spec_hash,
            parent_report_hash=hash_bytes(report_bytes),
        ).to_dict(),
    )
    confirmation = ExperimentSpec.from_dict(payload)
    request = ConfirmationRequest(
        discovery_experiment_id=discovery.experiment_id,
        discovery_spec_hash=discovery.spec_hash,
        discovery_report_hash=hash_bytes(report_bytes),
        discovery_run_hash=discovery_run.run_hash,
        discovery_dataset_hash=discovery_run.dataset_hash,
        confirmation_experiment_id=confirmation.experiment_id,
        confirmation_spec_hash=confirmation.spec_hash,
        confirmation_dataset_id=confirmation_dataset_id,
        confirmation_dataset_hash=confirmation_manifest.dataset_hash,
        requested_at=created_at,
    )
    created: list[Path] = []
    try:
        if _write_immutable_json(spec_output_path, confirmation.to_dict()):
            created.append(Path(spec_output_path))
        if _write_immutable_json(request_output_path, request.to_dict()):
            created.append(Path(request_output_path))
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    return confirmation, request


def run_reviewed_experiment(
    *,
    spec_path: Path,
    review_path: Path,
    dataset_directory: Path,
    dataset_id: str,
    output_directory: Path,
    code_commit: str,
    confirmation_request_path: Path | None = None,
):
    spec, review = load_reviewed_spec(spec_path, review_path)
    manifest, address = load_content_addressed_dataset(dataset_directory, dataset_id)
    if not manifest.point_in_time_data:
        raise ResearchOrchestrationError("reviewed runs require point-in-time data")
    if spec.mode == "confirmation":
        if confirmation_request_path is None:
            raise ResearchOrchestrationError(
                "confirmation run requires its immutable confirmation request"
            )
        request = ConfirmationRequest.from_dict(
            _read_json(confirmation_request_path, "confirmation request")
        )
        if (
            request.confirmation_spec_hash != spec.spec_hash
            or request.confirmation_experiment_id != spec.experiment_id
            or request.confirmation_dataset_hash != manifest.dataset_hash
            or request.confirmation_dataset_id != dataset_id
        ):
            raise ResearchOrchestrationError(
                "confirmation spec/dataset does not match its frozen request"
            )
    elif confirmation_request_path is not None:
        raise ResearchOrchestrationError(
            "discovery run must not carry a confirmation request"
        )
    baselines = dict(spec.baseline_columns)
    record = run_experiment(
        spec,
        dataset_directory,
        output_directory,
        code_commit,
        dataset_id=dataset_id,
        feature_columns=spec.ordered_feature_names,
        target_column=spec.target_column,
        trailing_baseline_column=baselines.get("trailing_realized"),
        ewma_baseline_column=baselines.get("ewma"),
    )
    return record, MappingProxyType(
        {
            "spec_hash": spec.spec_hash,
            "review_hash": review.review_hash,
            "dataset_hash": address.dataset_hash,
            "run_hash": record.run_hash,
            "verdict": record.verdict,
            "production_authoritative": False,
        }
    )
