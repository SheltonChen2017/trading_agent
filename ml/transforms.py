"""Leakage-safe cross-sectional and learned feature transforms.

Cross-sectional ranks and robust z-scores are computed independently within
each ``as_of_session``. Learned standardization is deliberately split into a
fit step that accepts explicit training row indices and an apply step; there
is no convenience API that fits on the full dataset before a walk-forward
split.
"""
from __future__ import annotations

import dataclasses
import math
from types import MappingProxyType
from typing import Mapping, Sequence

import numpy as np
import pandas as pd


class TransformError(ValueError):
    """Feature data cannot support a requested leakage-safe transform."""


def _validate_keys(frame: pd.DataFrame) -> None:
    missing = [name for name in ("as_of_session", "ticker") if name not in frame]
    if missing:
        raise TransformError(f"feature frame is missing key column(s): {missing}")
    if frame.empty:
        raise TransformError("feature frame has no rows")
    if frame[["as_of_session", "ticker"]].isna().any().any():
        raise TransformError("feature frame has missing as_of_session or ticker")
    sessions = pd.to_datetime(
        frame["as_of_session"], format="%Y-%m-%d", errors="coerce"
    )
    if sessions.isna().any() or not sessions.dt.strftime("%Y-%m-%d").equals(
        frame["as_of_session"]
    ):
        raise TransformError("as_of_session must use canonical YYYY-MM-DD format")
    if frame.duplicated(["as_of_session", "ticker"]).any():
        raise TransformError("feature frame has duplicate (as_of_session, ticker) rows")


def _validate_feature_names(
    frame: pd.DataFrame, feature_names: Sequence[str]
) -> tuple[str, ...]:
    if not isinstance(feature_names, (list, tuple)) or not feature_names:
        raise TransformError("feature_names must contain at least one column name")
    names = tuple(feature_names)
    if len(names) != len(set(names)):
        raise TransformError("feature_names contains duplicates")
    for name in names:
        if not isinstance(name, str) or not name.strip():
            raise TransformError("feature_names must contain non-empty strings")
        if name not in frame:
            raise TransformError(f"feature frame is missing feature {name!r}")
        numeric = pd.to_numeric(frame[name], errors="coerce")
        invalid = frame[name].notna() & numeric.isna()
        if invalid.any():
            raise TransformError(f"feature {name!r} contains non-numeric values")
        if np.isinf(numeric.to_numpy(dtype=float, na_value=np.nan)).any():
            raise TransformError(f"feature {name!r} contains infinity")
    return names


def add_cross_sectional_transforms(
    frame: pd.DataFrame,
    feature_names: Sequence[str],
) -> pd.DataFrame:
    """Add within-session percentile ranks and robust z-scores.

    Missing source values remain missing. A session whose feature has zero
    median absolute deviation receives a missing robust z-score instead of an
    infinity or a fabricated zero.
    """
    _validate_keys(frame)
    names = _validate_feature_names(frame, feature_names)
    result = frame.copy()
    for name in names:
        numeric = pd.to_numeric(result[name], errors="coerce")
        result[f"{name}__xs_percentile"] = numeric.groupby(
            result["as_of_session"], sort=False
        ).rank(method="average", pct=True)
        median = numeric.groupby(result["as_of_session"], sort=False).transform("median")
        absolute_deviation = (numeric - median).abs()
        mad = absolute_deviation.groupby(
            result["as_of_session"], sort=False
        ).transform("median")
        denominator = (1.4826 * mad).replace(0.0, np.nan)
        result[f"{name}__xs_robust_z"] = (numeric - median) / denominator
    return result


@dataclasses.dataclass(frozen=True)
class TrainingStandardizer:
    """Parameters fitted from one explicit training fold only."""

    feature_names: tuple[str, ...]
    means: Mapping[str, float]
    scales: Mapping[str, float]
    training_row_count: int
    training_start: str
    training_end: str

    def __post_init__(self) -> None:
        names = tuple(self.feature_names)
        if not names or len(names) != len(set(names)):
            raise TransformError("feature_names must be non-empty and unique")
        if set(self.means) != set(names) or set(self.scales) != set(names):
            raise TransformError("means/scales must match feature_names exactly")
        for name in names:
            mean = float(self.means[name])
            scale = float(self.scales[name])
            if not math.isfinite(mean):
                raise TransformError(f"mean for {name!r} is not finite")
            if not math.isfinite(scale) or scale <= 0:
                raise TransformError(f"scale for {name!r} must be positive and finite")
        if isinstance(self.training_row_count, bool) or self.training_row_count < 1:
            raise TransformError("training_row_count must be positive")
        object.__setattr__(self, "feature_names", names)
        object.__setattr__(self, "means", MappingProxyType(dict(self.means)))
        object.__setattr__(self, "scales", MappingProxyType(dict(self.scales)))


def fit_training_standardizer(
    frame: pd.DataFrame,
    feature_names: Sequence[str],
    *,
    train_row_indices: Sequence[int],
) -> TrainingStandardizer:
    """Fit mean/population-std using only explicit walk-forward train rows."""
    _validate_keys(frame)
    names = _validate_feature_names(frame, feature_names)
    indices = tuple(train_row_indices)
    if not indices:
        raise TransformError("train_row_indices must not be empty")
    if any(isinstance(index, bool) or not isinstance(index, int) for index in indices):
        raise TransformError("train_row_indices must contain integers")
    if len(indices) != len(set(indices)):
        raise TransformError("train_row_indices contains duplicates")
    if min(indices) < 0 or max(indices) >= len(frame):
        raise TransformError("train_row_indices contains an out-of-range row")

    training = frame.iloc[list(indices)]
    means: dict[str, float] = {}
    scales: dict[str, float] = {}
    for name in names:
        numeric = pd.to_numeric(training[name], errors="coerce")
        finite = numeric[np.isfinite(numeric)]
        if finite.empty:
            raise TransformError(f"training rows have no finite values for {name!r}")
        mean = float(finite.mean())
        scale = float(finite.std(ddof=0))
        means[name] = mean
        scales[name] = scale if scale > 0 else 1.0

    training_sessions = training["as_of_session"]
    return TrainingStandardizer(
        feature_names=names,
        means=means,
        scales=scales,
        training_row_count=len(training),
        training_start=str(training_sessions.min()),
        training_end=str(training_sessions.max()),
    )


def apply_training_standardizer(
    frame: pd.DataFrame,
    standardizer: TrainingStandardizer,
) -> pd.DataFrame:
    """Add standardized columns using already-fitted training parameters."""
    _validate_keys(frame)
    _validate_feature_names(frame, standardizer.feature_names)
    result = frame.copy()
    for name in standardizer.feature_names:
        numeric = pd.to_numeric(result[name], errors="coerce")
        result[f"{name}__standardized"] = (
            numeric - standardizer.means[name]
        ) / standardizer.scales[name]
    return result
