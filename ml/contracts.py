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
import re
from datetime import date, datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from assistant.schemas import EvidenceStatus

SCHEMA_VERSION = "1.0"
_SUPPORTED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ContractError(ValueError):
    """A manifest or prediction record failed its contract check."""


def _check_schema_version(schema_version: str) -> None:
    if schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
        raise ContractError(
            f"unknown schema_version {schema_version!r}; "
            f"supported: {sorted(_SUPPORTED_SCHEMA_VERSIONS)}"
        )


def _check_required_str(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{name} is required and must be a non-empty string")


def _check_bool(value: Any, name: str) -> None:
    if not isinstance(value, bool):
        raise ContractError(f"{name} must be a boolean")


def _check_int(value: Any, name: str, *, minimum: int = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractError(f"{name} must be an integer >= {minimum}")


def _check_nonnegative_number(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{name} must be a non-negative finite number")
    if not math.isfinite(float(value)) or value < 0:
        raise ContractError(f"{name} must be a non-negative finite number")


def _check_sha256(value: Any, name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ContractError(f"{name} must be a lowercase 64-character sha256 digest")


def _parse_date(value: Any, name: str) -> date:
    _check_required_str(value, name)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{name} must be an ISO-8601 date") from exc


def _parse_timestamp(value: Any, name: str) -> datetime:
    _check_required_str(value, name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{name} must be timezone-aware")
    return parsed


def _freeze_json(value: Any, *, path: str) -> Any:
    """Validate and recursively freeze one JSON-like value.

    ``frozen=True`` protects dataclass attribute assignment only. Without this
    copy/freeze step, a caller could mutate a manifest's nested dict after
    validation, including inserting NaN or changing a model parameter while
    retaining the same object identity.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError(f"{path} is not finite: {value!r}")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContractError(f"{path} contains non-string key {key!r}")
            frozen[key] = _freeze_json(item, path=f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    raise ContractError(
        f"{path} contains unsupported JSON value of type {type(value).__name__}"
    )


def _required_string_tuple(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ContractError(f"{name} must contain at least one string")
    result = tuple(value)
    for index, item in enumerate(result):
        _check_required_str(item, f"{name}[{index}]")
    return result


def _string_mapping(value: Any, name: str, *, require_nonempty: bool) -> Mapping[str, str]:
    if not isinstance(value, Mapping) or (require_nonempty and not value):
        qualifier = "a non-empty" if require_nonempty else "a"
        raise ContractError(f"{name} must be {qualifier} string mapping")
    result: dict[str, str] = {}
    for key, item in value.items():
        _check_required_str(key, f"{name} key")
        _check_required_str(item, f"{name}.{key}")
        result[key] = item
    return MappingProxyType(result)


def _window(value: Any, name: str) -> Mapping[str, str]:
    result = _string_mapping(value, name, require_nonempty=True)
    if set(result) != {"start", "end"}:
        raise ContractError(f"{name} must contain exactly 'start' and 'end'")
    start = _parse_date(result["start"], f"{name}.start")
    end = _parse_date(result["end"], f"{name}.end")
    if start > end:
        raise ContractError(f"{name}.start must not be after {name}.end")
    return result


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
        _check_required_str(self.universe_definition, "universe_definition")
        _check_required_str(self.entry_timing, "entry_timing")
        _check_required_str(self.tax_assumptions, "tax_assumptions")
        _check_required_str(self.git_commit, "git_commit")
        _parse_timestamp(self.created_at, "created_at")
        _check_bool(self.point_in_time_data, "point_in_time_data")
        requested_start = _parse_date(self.requested_start_date, "requested_start_date")
        requested_end = _parse_date(self.requested_end_date, "requested_end_date")
        actual_start = _parse_date(self.actual_start_date, "actual_start_date")
        actual_end = _parse_date(self.actual_end_date, "actual_end_date")
        if requested_start > requested_end:
            raise ContractError("requested_start_date must not be after requested_end_date")
        if actual_start > actual_end:
            raise ContractError("actual_start_date must not be after actual_end_date")
        _check_int(self.row_count, "row_count")
        _check_int(self.distinct_session_count, "distinct_session_count")
        _check_int(self.ticker_count, "ticker_count")
        if self.row_count == 0 and (self.distinct_session_count or self.ticker_count):
            raise ContractError("empty datasets cannot declare sessions or tickers")
        if self.row_count > 0 and (
            self.distinct_session_count == 0 or self.ticker_count == 0
        ):
            raise ContractError("non-empty datasets must declare sessions and tickers")
        if self.distinct_session_count > self.row_count or self.ticker_count > self.row_count:
            raise ContractError("session/ticker counts cannot exceed row_count")
        _check_int(self.target_horizon_sessions, "target_horizon_sessions", minimum=1)
        _check_int(self.embargo_sessions, "embargo_sessions")
        if self.embargo_sessions < self.target_horizon_sessions:
            raise ContractError(
                "embargo_sessions must be at least target_horizon_sessions"
            )
        _check_nonnegative_number(self.transaction_cost_bps, "transaction_cost_bps")
        _check_sha256(self.dataset_hash, "dataset_hash")
        sources = _required_string_tuple(self.source_descriptions, "source_descriptions")
        hashes = _string_mapping(self.input_hashes, "input_hashes", require_nonempty=True)
        for key, digest in hashes.items():
            _check_sha256(digest, f"input_hashes.{key}")
        object.__setattr__(self, "source_descriptions", sources)
        object.__setattr__(self, "input_hashes", hashes)

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
            # Presence is checked here so the resulting error identifies the
            # missing field. Shape/type validation remains in __post_init__;
            # coercing a string with tuple("prices") would otherwise turn it
            # into valid-looking one-character descriptions.
            _ = kwargs["source_descriptions"]
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
        _check_required_str(self.feature_set_version, "feature_set_version")
        _check_required_str(self.label_version, "label_version")
        _check_required_str(self.algorithm, "algorithm")
        _parse_timestamp(self.created_at, "created_at")
        _check_sha256(self.dataset_hash, "dataset_hash")
        _check_sha256(self.artifact_hash, "artifact_hash")
        _check_sha256(self.evaluation_report_hash, "evaluation_report_hash")
        feature_names = _required_string_tuple(
            self.ordered_feature_names, "ordered_feature_names"
        )
        if len(set(feature_names)) != len(feature_names):
            raise ContractError("ordered_feature_names must not contain duplicates")
        _check_int(self.random_seed, "random_seed")
        _check_evidence_status(self.evidence_status)
        hyperparameters = _freeze_json(self.hyperparameters, path="hyperparameters")
        if not isinstance(hyperparameters, Mapping):
            raise ContractError("hyperparameters must be a JSON object")
        training_window = _window(self.training_window, "training_window")
        if not isinstance(self.validation_windows, (list, tuple)) or not self.validation_windows:
            raise ContractError("validation_windows must contain at least one window")
        validation_windows = tuple(
            _window(window, f"validation_windows[{index}]")
            for index, window in enumerate(self.validation_windows)
        )
        dependency_versions = _string_mapping(
            self.dependency_versions, "dependency_versions", require_nonempty=True
        )
        object.__setattr__(self, "ordered_feature_names", feature_names)
        object.__setattr__(self, "hyperparameters", hyperparameters)
        object.__setattr__(self, "training_window", training_window)
        object.__setattr__(self, "validation_windows", validation_windows)
        object.__setattr__(self, "dependency_versions", dependency_versions)

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
        if payload.get("production_authoritative", False) is not False:
            raise ContractError("ModelManifest production_authoritative must be false")
        try:
            kwargs = {k: v for k, v in payload.items() if k != "production_authoritative"}
            _ = kwargs["ordered_feature_names"]
            _ = kwargs["validation_windows"]
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
        _check_required_str(
            self.dataset_or_feature_snapshot_hash,
            "dataset_or_feature_snapshot_hash",
        )
        _check_required_str(self.task, "task")
        _check_required_str(self.subject_key, "subject_key")
        _check_sha256(self.artifact_hash, "artifact_hash")
        _check_sha256(
            self.dataset_or_feature_snapshot_hash,
            "dataset_or_feature_snapshot_hash",
        )
        _parse_date(self.as_of_session, "as_of_session")
        generated_at = _parse_timestamp(self.generated_at, "generated_at")
        data_available_at = _parse_timestamp(
            self.data_available_at, "data_available_at"
        )
        if data_available_at > generated_at:
            raise ContractError("data_available_at must not be after generated_at")
        _check_int(self.horizon_sessions, "horizon_sessions", minimum=1)
        _check_bool(self.available, "available")
        if not isinstance(self.refusal_reasons, (list, tuple)):
            raise ContractError("refusal_reasons must be an array of strings")
        refusal_reasons = tuple(self.refusal_reasons)
        for index, reason in enumerate(refusal_reasons):
            _check_required_str(reason, f"refusal_reasons[{index}]")
        if len(set(refusal_reasons)) != len(refusal_reasons):
            raise ContractError("refusal_reasons must not contain duplicates")
        values = _freeze_json(self.values, path="values")
        uncertainty = _freeze_json(self.uncertainty, path="uncertainty")
        feature_freshness = _freeze_json(
            self.feature_freshness, path="feature_freshness"
        )
        if not isinstance(values, Mapping) or not isinstance(uncertainty, Mapping):
            raise ContractError("values and uncertainty must be JSON objects")
        if not isinstance(feature_freshness, Mapping):
            raise ContractError("feature_freshness must be a JSON object")
        if not self.available and not self.refusal_reasons:
            raise ContractError(
                "an unavailable prediction must record at least one refusal reason "
                "(strategy doc 3.3: missing/stale/non-finite features must produce "
                "an unavailable prediction, never a silent default)"
            )
        if self.available and refusal_reasons:
            raise ContractError(
                "an available prediction must not carry refusal_reasons"
            )
        if self.available:
            if not values:
                raise ContractError("an available prediction must carry values")
            if not feature_freshness:
                raise ContractError(
                    "an available prediction must carry feature_freshness"
                )
        elif values or uncertainty:
            raise ContractError(
                "an unavailable prediction must not carry values or uncertainty"
            )
        _check_evidence_status(self.evidence_status)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "uncertainty", uncertainty)
        object.__setattr__(self, "feature_freshness", feature_freshness)
        object.__setattr__(self, "refusal_reasons", refusal_reasons)

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
        if payload.get("production_authoritative", False) is not False:
            raise ContractError("PredictionRecord production_authoritative must be false")
        try:
            kwargs = {k: v for k, v in payload.items() if k != "production_authoritative"}
            _ = kwargs["refusal_reasons"]
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
