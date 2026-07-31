"""Frozen, JSON-serializable contracts for the ML observation layer.

Machine learning enters this application only as versioned, auditable
observations -- never as trade authority (docs/ML_IMPLEMENTATION_STRATEGY.md
section 1). This module owns the three artifacts that make every ML output
auditable and non-authoritative by construction:

- DatasetManifest: what data went into a training/evaluation run.
- ModelManifest: what model was fit, on what data, with what evaluation.
- PredictionRecord: one typed observation, always production_authoritative=False.

`production_authoritative` is exposed only as an always-False `@property` on
ModelManifest and PredictionRecord -- there is no constructor parameter, so
ordinary training/inference code cannot set it to True (strategy doc section
5.3: "Make production_authoritative impossible to set to true from ordinary
model training or inference code"). Authority can only come from a future,
separate promotion decision outside this module (ML-10 in the strategy doc;
not yet built).
"""
from __future__ import annotations

import dataclasses
import math
from enum import Enum
from typing import Any, Mapping, Sequence

from assistant.schemas import EvidenceStatus

SCHEMA_VERSION = "1.0"
_SUPPORTED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})


class ContractError(ValueError):
    """A manifest or prediction record failed its contract check."""


def _check_finite(value: Any, *, path: str = "value") -> None:
    """Recursively reject NaN/inf anywhere in a JSON-serializable structure.

    Strategy doc section 5.5: "rejection of NaN and infinity anywhere in
    numeric output" -- not just at the top level of a manifest.
    """
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError(f"{path} is not finite: {value!r}")
        return
    if isinstance(value, (int, str)) or value is None:
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _check_finite(item, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _check_finite(item, path=f"{path}[{index}]")
        return
    # Anything else (e.g. an Enum) is not a numeric leaf this check owns;
    # to_dict()/JSON serialization is the backstop for unrecognized types.


def _check_schema_version(schema_version: str) -> None:
    if schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
        raise ContractError(
            f"unknown schema_version {schema_version!r}; "
            f"supported: {sorted(_SUPPORTED_SCHEMA_VERSIONS)}"
        )


def _check_required_str(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{name} is required and must be a non-empty string")


def _check_evidence_status(value: Any) -> None:
    if not isinstance(value, EvidenceStatus):
        raise ContractError(
            "evidence_status must be an assistant.schemas.EvidenceStatus, "
            f"got {value!r}"
        )


def _to_dict(obj: Any) -> Any:
    """Recursively convert dataclasses (including nested ones, lists, dicts,
    Mappings, and Enums) into plain JSON-serializable structures.

    Mirrors assistant/schemas.py's own `_to_dict()`: walks
    `dataclasses.fields()` one field at a time and recurses through this
    function, rather than calling `dataclasses.asdict()` up front, so a
    nested dataclass is still a real instance (not yet a plain dict) when
    this function's own per-type checks run on it -- the same ordering bug
    assistant/schemas.py's docstring documents avoiding for
    `SignalEvidence.production_authoritative`. `ModelManifest` and
    `PredictionRecord` have the identical shape here: their
    `production_authoritative` is a `@property`, not a dataclass field, so
    it does not appear from `dataclasses.fields()` alone and must be added
    explicitly.
    """
    if dataclasses.is_dataclass(obj):
        result = {f.name: _to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
        if isinstance(obj, (ModelManifest, PredictionRecord)):
            result["production_authoritative"] = obj.production_authoritative
        return result
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (list, tuple)):
        return [_to_dict(v) for v in obj]
    if isinstance(obj, Mapping):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


@dataclasses.dataclass(frozen=True)
class DatasetManifest:
    """What data went into a training/evaluation run (strategy doc 5.3)."""

    dataset_id: str
    created_at: str
    task: str
    feature_set_version: str
    label_version: str
    source_descriptions: tuple[str, ...]
    point_in_time_data: bool
    requested_start_date: str
    requested_end_date: str
    actual_start_date: str
    actual_end_date: str
    row_count: int
    distinct_session_count: int
    ticker_count: int
    universe_definition: str
    entry_timing: str
    target_horizon_sessions: int
    embargo_sessions: int
    transaction_cost_bps: float
    tax_assumptions: str
    input_hashes: Mapping[str, str]
    dataset_hash: str
    git_commit: str
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _check_schema_version(self.schema_version)
        _check_required_str(self.dataset_id, "dataset_id")
        _check_required_str(self.created_at, "created_at")
        _check_required_str(self.task, "task")
        _check_required_str(self.feature_set_version, "feature_set_version")
        _check_required_str(self.label_version, "label_version")
        _check_required_str(self.dataset_hash, "dataset_hash")
        _check_required_str(self.git_commit, "git_commit")
        if self.row_count < 0 or self.distinct_session_count < 0 or self.ticker_count < 0:
            raise ContractError("row_count/distinct_session_count/ticker_count must be >= 0")
        if self.target_horizon_sessions < 1:
            raise ContractError("target_horizon_sessions must be a positive integer")
        if self.embargo_sessions < 0:
            raise ContractError("embargo_sessions must be >= 0")
        _check_finite(self.transaction_cost_bps, path="transaction_cost_bps")
        _check_finite(dict(self.input_hashes), path="input_hashes")

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DatasetManifest":
        if not isinstance(payload, Mapping):
            raise ContractError("DatasetManifest payload must be a JSON object")
        fields = {f.name for f in dataclasses.fields(cls)}
        unknown = set(payload) - fields
        if unknown:
            raise ContractError(f"DatasetManifest payload has unknown fields: {sorted(unknown)}")
        try:
            kwargs = dict(payload)
            kwargs["source_descriptions"] = tuple(kwargs["source_descriptions"])
        except KeyError as exc:
            raise ContractError(f"DatasetManifest payload missing required field: {exc}") from exc
        try:
            return cls(**kwargs)
        except TypeError as exc:
            raise ContractError(f"DatasetManifest payload missing required field(s): {exc}") from exc


@dataclasses.dataclass(frozen=True)
class ModelManifest:
    """What model was fit, on what data, with what evaluation (5.3).

    `production_authoritative` is deliberately not a constructor field --
    see module docstring.
    """

    model_id: str
    model_version: str
    task: str
    created_at: str
    dataset_id: str
    dataset_hash: str
    feature_set_version: str
    ordered_feature_names: tuple[str, ...]
    label_version: str
    algorithm: str
    hyperparameters: Mapping[str, Any]
    random_seed: int
    training_window: Mapping[str, str]
    validation_windows: tuple[Mapping[str, str], ...]
    dependency_versions: Mapping[str, str]
    artifact_hash: str
    evaluation_report_hash: str
    evidence_status: EvidenceStatus
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _check_schema_version(self.schema_version)
        _check_required_str(self.model_id, "model_id")
        _check_required_str(self.model_version, "model_version")
        _check_required_str(self.task, "task")
        _check_required_str(self.created_at, "created_at")
        _check_required_str(self.dataset_id, "dataset_id")
        _check_required_str(self.dataset_hash, "dataset_hash")
        _check_required_str(self.feature_set_version, "feature_set_version")
        _check_required_str(self.label_version, "label_version")
        _check_required_str(self.algorithm, "algorithm")
        _check_required_str(self.artifact_hash, "artifact_hash")
        _check_required_str(self.evaluation_report_hash, "evaluation_report_hash")
        if not self.ordered_feature_names:
            raise ContractError("ordered_feature_names must not be empty")
        if len(set(self.ordered_feature_names)) != len(self.ordered_feature_names):
            raise ContractError("ordered_feature_names must not contain duplicates")
        _check_evidence_status(self.evidence_status)
        _check_finite(dict(self.hyperparameters), path="hyperparameters")

    @property
    def production_authoritative(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelManifest":
        if not isinstance(payload, Mapping):
            raise ContractError("ModelManifest payload must be a JSON object")
        # production_authoritative is a computed property, not a constructor
        # field -- to_dict() includes it for JSON consumers, but round-
        # tripping through the constructor must ignore it rather than pass
        # it through as an unexpected kwarg.
        fields = {f.name for f in dataclasses.fields(cls)}
        unknown = set(payload) - fields - {"production_authoritative"}
        if unknown:
            raise ContractError(f"ModelManifest payload has unknown fields: {sorted(unknown)}")
        try:
            kwargs = {k: v for k, v in payload.items() if k != "production_authoritative"}
            kwargs["ordered_feature_names"] = tuple(kwargs["ordered_feature_names"])
            kwargs["validation_windows"] = tuple(
                dict(window) for window in kwargs["validation_windows"]
            )
            kwargs["evidence_status"] = EvidenceStatus(kwargs["evidence_status"])
        except KeyError as exc:
            raise ContractError(f"ModelManifest payload missing required field: {exc}") from exc
        except ValueError as exc:
            raise ContractError(f"ModelManifest payload has invalid evidence_status: {exc}") from exc
        try:
            return cls(**kwargs)
        except TypeError as exc:
            raise ContractError(f"ModelManifest payload missing required field(s): {exc}") from exc


@dataclasses.dataclass(frozen=True)
class PredictionRecord:
    """One typed observation (5.3). Always production_authoritative=False --
    see module docstring.
    """

    prediction_id: str
    model_id: str
    model_version: str
    artifact_hash: str
    dataset_or_feature_snapshot_hash: str
    task: str
    subject_key: str
    as_of_session: str
    generated_at: str
    horizon_sessions: int
    values: Mapping[str, Any]
    uncertainty: Mapping[str, Any]
    data_available_at: str
    feature_freshness: Mapping[str, Any]
    available: bool
    refusal_reasons: tuple[str, ...]
    evidence_status: EvidenceStatus
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _check_schema_version(self.schema_version)
        _check_required_str(self.prediction_id, "prediction_id")
        _check_required_str(self.model_id, "model_id")
        _check_required_str(self.model_version, "model_version")
        _check_required_str(self.artifact_hash, "artifact_hash")
        _check_required_str(self.task, "task")
        _check_required_str(self.subject_key, "subject_key")
        _check_required_str(self.as_of_session, "as_of_session")
        _check_required_str(self.generated_at, "generated_at")
        _check_required_str(self.data_available_at, "data_available_at")
        if self.horizon_sessions < 1:
            raise ContractError("horizon_sessions must be a positive integer")
        if not self.available and not self.refusal_reasons:
            raise ContractError(
                "an unavailable prediction must record at least one refusal reason "
                "(strategy doc 3.3: missing/stale/non-finite features must produce "
                "an unavailable prediction, never a silent default)"
            )
        if self.available and self.refusal_reasons:
            raise ContractError(
                "an available prediction must not carry refusal_reasons"
            )
        if self.available:
            if not self.values:
                raise ContractError("an available prediction must carry values")
            _check_finite(dict(self.values), path="values")
            _check_finite(dict(self.uncertainty), path="uncertainty")
        _check_evidence_status(self.evidence_status)

    @property
    def production_authoritative(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PredictionRecord":
        if not isinstance(payload, Mapping):
            raise ContractError("PredictionRecord payload must be a JSON object")
        fields = {f.name for f in dataclasses.fields(cls)}
        unknown = set(payload) - fields - {"production_authoritative"}
        if unknown:
            raise ContractError(f"PredictionRecord payload has unknown fields: {sorted(unknown)}")
        try:
            kwargs = {k: v for k, v in payload.items() if k != "production_authoritative"}
            kwargs["refusal_reasons"] = tuple(kwargs["refusal_reasons"])
            kwargs["evidence_status"] = EvidenceStatus(kwargs["evidence_status"])
        except KeyError as exc:
            raise ContractError(f"PredictionRecord payload missing required field: {exc}") from exc
        except ValueError as exc:
            raise ContractError(f"PredictionRecord payload has invalid evidence_status: {exc}") from exc
        try:
            return cls(**kwargs)
        except TypeError as exc:
            raise ContractError(f"PredictionRecord payload missing required field(s): {exc}") from exc


def require_matching_feature_order(
    manifest: ModelManifest, feature_names: Sequence[str]
) -> None:
    """Refuse to score a row/frame built with a different feature order than
    the model was trained on (strategy doc 5.5: "ordered feature mismatch
    refusal"). A silent column-order mismatch would feed each numeric value
    to sklearn labeled as the wrong feature without raising anything."""
    if tuple(feature_names) != manifest.ordered_feature_names:
        raise ContractError(
            "feature order mismatch: model "
            f"{manifest.model_id}/{manifest.model_version} expects "
            f"{manifest.ordered_feature_names}, got {tuple(feature_names)}"
        )
