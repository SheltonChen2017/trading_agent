"""Strict prospective inference evidence for ML-FS-5.

The contract in this module is deliberately separate from trading intent.  It
describes what a model knew and emitted at one scheduled cutoff; it contains no
side, quantity, approval, order, or execution field and is always
``production_authoritative=False``.
"""
from __future__ import annotations

import dataclasses
import math
from datetime import date, datetime
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

from ml.hashing import canonical_json, hash_payload
from ml.volatility_evaluation import (
    MIN_RESIDUALS_FOR_INTERVAL,
    CalibrationStatus,
)

PROSPECTIVE_SCHEMA_VERSION = "1"
DAILY_VOLATILITY_UNIT = "daily_return_standard_deviation_pct"
_LINEAGE_KEYS = frozenset(
    {
        "model_key",
        "provider_id",
        "dataset_id",
        "dataset_hash",
        "artifact_hash",
        "evaluation_report_hash",
        "feature_set_version",
        "label_version",
        "configuration_hash",
        "evidence_epoch",
        "shadow_run_id",
        "feature_snapshot_hash",
        "schedule_version",
    }
)
_ACTION_FIELDS = frozenset(
    {"side", "shares", "quantity", "execute", "approved", "order_type", "limit_price"}
)


class ProspectiveContractError(ValueError):
    """A prospective prediction or its frozen uncertainty profile is invalid."""


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ProspectiveContractError(f"{name} must be a non-empty trimmed string")
    return value


def _finite(value: Any, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProspectiveContractError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise ProspectiveContractError(f"{name} must be a finite number >= {minimum}")
    return result


def _instant(value: Any, name: str) -> str:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProspectiveContractError(f"{name} must be timezone-aware ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProspectiveContractError(f"{name} must be timezone-aware ISO-8601")
    return text


def build_volatility_prospective_profile(
    fold_predictions: Sequence[Mapping[str, Any]],
    *,
    ceiling_calibration: Mapping[str, Any],
    target_coverage: float = 0.90,
) -> dict[str, Any]:
    """Freeze deployable uncertainty inputs from untouched OOF predictions.

    Residuals are appended only after each validation fold has been scored by
    the experiment runner.  Persisting the final OOF residual population in
    the artifact lets prospective inference calculate intervals and threshold
    probabilities without consulting later realized outcomes.
    """
    if not 0 < float(target_coverage) < 1:
        raise ProspectiveContractError("target_coverage must be in (0, 1)")
    residuals: list[float] = []
    for fold in fold_predictions:
        actual = np.asarray(fold.get("actual", ()), dtype=float)
        predicted = np.asarray(fold.get("predicted", ()), dtype=float)
        if actual.shape != predicted.shape:
            raise ProspectiveContractError("OOF actual and predicted arrays must align")
        usable = (
            np.isfinite(actual)
            & np.isfinite(predicted)
            & (actual > 0)
            & (predicted > 0)
        )
        residuals.extend(np.log(actual[usable] / predicted[usable]).tolist())
    residuals = sorted(float(value) for value in residuals)
    tail = (1.0 - float(target_coverage)) / 2.0
    interval: dict[str, Any]
    if len(residuals) >= MIN_RESIDUALS_FOR_INTERVAL:
        interval = {
            "status": "available",
            "method": "out_of_fold_empirical_log_residual",
            "target_coverage": float(target_coverage),
            "log_residual_quantiles": [
                float(np.quantile(residuals, tail)),
                float(np.quantile(residuals, 1.0 - tail)),
            ],
            "residual_count": len(residuals),
        }
    else:
        interval = {
            "status": "unavailable",
            "method": "out_of_fold_empirical_log_residual",
            "target_coverage": float(target_coverage),
            "log_residual_quantiles": None,
            "residual_count": len(residuals),
            "reason": "insufficient_out_of_fold_residuals",
        }

    calibration = dict(ceiling_calibration)
    status = calibration.get("calibration_status")
    if status not in CalibrationStatus.ALL:
        raise ProspectiveContractError("ceiling calibration has no recognized status")
    ceiling = calibration.get("ceiling_pct")
    threshold = {
        "status": "available" if ceiling is not None and residuals else "unavailable",
        "method": "out_of_fold_empirical_log_residual",
        "ceiling_daily_pct": ceiling,
        "calibration_status": status,
        "brier_score": calibration.get("brier_score"),
        "event_count": calibration.get("event_count", 0),
        "empirical_log_residuals": residuals,
    }
    if threshold["status"] == "unavailable":
        threshold["reason"] = (
            "no_preregistered_ceiling"
            if ceiling is None
            else "no_out_of_fold_residuals"
        )
    profile = {
        "schema_version": PROSPECTIVE_SCHEMA_VERSION,
        "interval": interval,
        "threshold": threshold,
    }
    canonical_json(profile)
    return profile


def derive_volatility_uncertainty(
    point_daily_pct: float, profile: Mapping[str, Any]
) -> dict[str, Any]:
    """Derive the frozen interval and ceiling probability for one point."""
    point = _finite(point_daily_pct, "point_daily_pct", minimum=0.0)
    if not isinstance(profile, Mapping) or profile.get("schema_version") != PROSPECTIVE_SCHEMA_VERSION:
        raise ProspectiveContractError("model artifact lacks a supported prospective profile")
    interval = profile.get("interval")
    threshold = profile.get("threshold")
    if not isinstance(interval, Mapping) or interval.get("status") != "available":
        raise ProspectiveContractError("prospective prediction interval is unavailable")
    quantiles = interval.get("log_residual_quantiles")
    if not isinstance(quantiles, (list, tuple)) or len(quantiles) != 2:
        raise ProspectiveContractError("prospective interval quantiles are invalid")
    low, high = (_finite(value, "log residual quantile") for value in quantiles)
    lower = point * math.exp(low)
    upper = point * math.exp(high)
    if not lower <= point <= upper:
        raise ProspectiveContractError("prospective interval does not contain the point")
    if not isinstance(threshold, Mapping) or threshold.get("status") != "available":
        raise ProspectiveContractError("prospective threshold probability is unavailable")
    ceiling = _finite(threshold.get("ceiling_daily_pct"), "ceiling_daily_pct", minimum=0.0)
    residuals = np.asarray(threshold.get("empirical_log_residuals", ()), dtype=float)
    if residuals.size == 0 or not np.isfinite(residuals).all():
        raise ProspectiveContractError("prospective threshold residuals are unavailable")
    probability = float(np.mean(point * np.exp(residuals) > ceiling))
    calibration_status = threshold.get("calibration_status")
    if calibration_status not in CalibrationStatus.ALL:
        raise ProspectiveContractError("prospective calibration status is invalid")
    return {
        "profile_hash": hash_payload(dict(profile)),
        "prediction_interval_daily_pct": [round(lower, 6), round(upper, 6)],
        "target_coverage": float(interval["target_coverage"]),
        "threshold_probability": round(probability, 6),
        "probability_label": (
            "calibrated_probability"
            if calibration_status == CalibrationStatus.CALIBRATED
            else "experimental_probability"
        ),
        "ceiling_daily_pct": ceiling,
        "calibration_status": calibration_status,
        "calibration_brier_score": threshold.get("brier_score"),
        "calibration_event_count": threshold.get("event_count", 0),
    }


@dataclasses.dataclass(frozen=True)
class ProspectiveInferenceContract:
    prediction_id: str
    task: str
    subject_key: str
    as_of_session: str
    generated_at: str
    horizon_sessions: int
    target_available_at: str
    point_estimate: Mapping[str, Any] | None
    prediction_interval: Mapping[str, Any] | None
    threshold_probability: Mapping[str, Any] | None
    calibration: Mapping[str, Any]
    frozen_baselines: Mapping[str, Any]
    feature_observations: tuple[Mapping[str, Any], ...]
    reference_distribution: Mapping[str, Any]
    regime_category: str
    event_category: str
    lineage: Mapping[str, Any]
    available: bool
    refusal_reasons: tuple[str, ...] = ()
    schema_version: str = PROSPECTIVE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PROSPECTIVE_SCHEMA_VERSION:
            raise ProspectiveContractError("unsupported prospective schema_version")
        for name in ("prediction_id", "task", "subject_key"):
            _text(getattr(self, name), name)
        try:
            parsed_session = date.fromisoformat(self.as_of_session)
        except (TypeError, ValueError) as exc:
            raise ProspectiveContractError("as_of_session must use YYYY-MM-DD") from exc
        if parsed_session.isoformat() != self.as_of_session:
            raise ProspectiveContractError("as_of_session must use YYYY-MM-DD")
        _instant(self.generated_at, "generated_at")
        _instant(self.target_available_at, "target_available_at")
        if isinstance(self.horizon_sessions, bool) or not isinstance(self.horizon_sessions, int) or self.horizon_sessions < 1:
            raise ProspectiveContractError("horizon_sessions must be positive")
        if not isinstance(self.available, bool):
            raise ProspectiveContractError("available must be boolean")
        reasons = tuple(self.refusal_reasons)
        if any(not isinstance(reason, str) or not reason.strip() for reason in reasons):
            raise ProspectiveContractError("refusal_reasons must contain non-empty strings")
        if self.available == bool(reasons):
            raise ProspectiveContractError("available/refusal_reasons are inconsistent")
        if set(self.lineage) != _LINEAGE_KEYS:
            raise ProspectiveContractError(
                f"lineage keys must be exactly {sorted(_LINEAGE_KEYS)}"
            )
        for key, value in self.lineage.items():
            _text(value, f"lineage.{key}")
        if not self.feature_observations:
            raise ProspectiveContractError("feature_observations must not be empty")
        names: list[str] = []
        for index, feature in enumerate(self.feature_observations):
            if not isinstance(feature, Mapping):
                raise ProspectiveContractError(f"feature_observations[{index}] must be an object")
            name = _text(feature.get("name"), f"feature_observations[{index}].name")
            if name in _ACTION_FIELDS:
                raise ProspectiveContractError(
                    f"feature_observations[{index}].name is action-shaped"
                )
            names.append(name)
            if not isinstance(feature.get("missing"), bool):
                raise ProspectiveContractError(f"feature_observations[{index}].missing must be boolean")
            if feature["missing"]:
                if feature.get("value") is not None:
                    raise ProspectiveContractError("missing features cannot carry values")
            else:
                _finite(feature.get("value"), f"feature_observations[{index}].value")
                _instant(feature.get("available_at"), f"feature_observations[{index}].available_at")
                age = feature.get("age_sessions")
                if isinstance(age, bool) or not isinstance(age, int) or age < 0:
                    raise ProspectiveContractError("feature age_sessions must be non-negative")
        if len(set(names)) != len(names):
            raise ProspectiveContractError("feature_observations contain duplicate names")
        for mapping_name in (
            "calibration", "frozen_baselines", "reference_distribution", "lineage"
        ):
            value = getattr(self, mapping_name)
            if not isinstance(value, Mapping):
                raise ProspectiveContractError(f"{mapping_name} must be an object")
            canonical_json(dict(value))
        _text(self.regime_category, "regime_category")
        _text(self.event_category, "event_category")
        if self.available:
            if self.point_estimate is None or self.prediction_interval is None or self.threshold_probability is None:
                raise ProspectiveContractError("available predictions require point, interval, and probability")
            point = _finite(self.point_estimate.get("value"), "point_estimate.value", minimum=0.0)
            if self.point_estimate.get("unit") != DAILY_VOLATILITY_UNIT:
                raise ProspectiveContractError("point estimate has the wrong unit")
            lower = _finite(self.prediction_interval.get("lower"), "prediction_interval.lower", minimum=0.0)
            upper = _finite(self.prediction_interval.get("upper"), "prediction_interval.upper", minimum=0.0)
            if not lower <= point <= upper:
                raise ProspectiveContractError("prediction interval must contain the point")
            probability = _finite(self.threshold_probability.get("value"), "threshold_probability.value", minimum=0.0)
            if probability > 1:
                raise ProspectiveContractError("threshold probability must be <= 1")
            if self.threshold_probability.get("label") not in {
                "experimental_probability", "calibrated_probability"
            }:
                raise ProspectiveContractError("threshold probability label is invalid")
            if any(feature.get("missing") for feature in self.feature_observations):
                raise ProspectiveContractError("available prediction cannot have missing features")
        elif any(value is not None for value in (
            self.point_estimate, self.prediction_interval, self.threshold_probability
        )):
            raise ProspectiveContractError("unavailable prediction cannot carry numeric predictions")
        payload = self.to_dict()
        if _ACTION_FIELDS & set(payload):
            raise ProspectiveContractError("prospective contract contains action-shaped fields")

        object.__setattr__(self, "refusal_reasons", reasons)
        object.__setattr__(self, "calibration", MappingProxyType(dict(self.calibration)))
        object.__setattr__(self, "frozen_baselines", MappingProxyType(dict(self.frozen_baselines)))
        object.__setattr__(self, "reference_distribution", MappingProxyType(dict(self.reference_distribution)))
        object.__setattr__(self, "lineage", MappingProxyType(dict(self.lineage)))
        object.__setattr__(self, "feature_observations", tuple(MappingProxyType(dict(value)) for value in self.feature_observations))

    @property
    def production_authoritative(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "prediction_id": self.prediction_id,
            "task": self.task,
            "subject_key": self.subject_key,
            "as_of_session": self.as_of_session,
            "generated_at": self.generated_at,
            "horizon_sessions": self.horizon_sessions,
            "target_available_at": self.target_available_at,
            "point_estimate": dict(self.point_estimate) if self.point_estimate is not None else None,
            "prediction_interval": dict(self.prediction_interval) if self.prediction_interval is not None else None,
            "threshold_probability": dict(self.threshold_probability) if self.threshold_probability is not None else None,
            "calibration": dict(self.calibration),
            "frozen_baselines": dict(self.frozen_baselines),
            "feature_observations": [dict(value) for value in self.feature_observations],
            "reference_distribution": dict(self.reference_distribution),
            "regime_category": self.regime_category,
            "event_category": self.event_category,
            "lineage": dict(self.lineage),
            "available": self.available,
            "refusal_reasons": list(self.refusal_reasons),
            "production_authoritative": False,
        }
