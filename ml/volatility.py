"""ML-4: volatility forecasting, evaluated against frozen baselines
(strategy doc section 8).

Model order is fixed by doc 8.2 and enforced by `evaluate_volatility_models()`
running all four in sequence on every fold: trailing realized vol, EWMA,
regularized regression on LOG volatility, and gradient boosting -- the last
"only if it beats the baselines", which is a decision this module reports
on rather than makes.

Regression targets log volatility, not volatility: volatility is bounded
below by zero and strongly right-skewed, so a linear model on the raw level
happily predicts negative volatility. Predictions are exponentiated back,
which also guarantees positivity structurally rather than by clipping.

Output is an observation, never an instruction (doc 3.2): the emitted dict
carries an estimate, an interval, a probability, an evidence status, and
`production_authoritative=False` -- and no side/quantity/approval field.
"""
from __future__ import annotations

import dataclasses
import math
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from ml.baselines import ewma_volatility_pct, trailing_realized_volatility_pct
from ml.evaluation import (
    interval_coverage,
    mean_absolute_error,
    qlike_loss,
)

PRIMARY_HORIZON_SESSIONS = 20  # doc 8.1: preregistered primary horizon
SUPPORTED_HORIZONS = (5, 10, 20)
# Per-security SESSION rows -- one security's own time series, so ~3 months
# of sessions. Deliberately unequal to ml/cross_sectional.py's
# MIN_TRAINING_ROWS (200), which counts pooled name-date rows; the two count
# different units and should not be reconciled to a shared number.
#
# A refusal floor, not a power calculation. Note these rows OVERLAP at the
# 20-session primary horizon, so 60 rows carry far fewer than 60 independent
# observations; purged walk-forward splitting and the interval/coverage
# reports are what actually judge sufficiency.
MIN_TRAINING_ROWS = 60


class VolatilityModelError(ValueError):
    """Inputs cannot support a volatility model fit or forecast."""


@dataclasses.dataclass(frozen=True)
class VolatilityForecast:
    """One observation. Mirrors doc 8.4's example payload exactly."""

    task: str
    subject_key: str
    horizon_sessions: int
    as_of_session: str
    annualized_volatility_pct: float | None
    prediction_interval_pct: tuple[float, float] | None
    probability_above_mandate_ceiling: float | None
    model_key: str
    evidence_status: str
    available: bool
    refusal_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("task", "subject_key", "as_of_session", "model_key", "evidence_status"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise VolatilityModelError(f"{name} must be a non-empty string")
        parsed = pd.to_datetime(
            self.as_of_session, format="%Y-%m-%d", errors="coerce"
        )
        if pd.isna(parsed) or parsed.strftime("%Y-%m-%d") != self.as_of_session:
            raise VolatilityModelError("as_of_session must use canonical YYYY-MM-DD format")
        if self.horizon_sessions not in SUPPORTED_HORIZONS:
            raise VolatilityModelError(
                f"horizon_sessions must be one of {SUPPORTED_HORIZONS}"
            )
        if self.evidence_status not in {
            "exploratory", "promising_unconfirmed", "rejected", "unavailable"
        }:
            raise VolatilityModelError(
                "evidence_status is not a recognized non-authoritative state"
            )
        if not isinstance(self.available, bool):
            raise VolatilityModelError("available must be a boolean")
        if not isinstance(self.refusal_reasons, tuple) or any(
            not isinstance(reason, str) or not reason.strip()
            for reason in self.refusal_reasons
        ):
            raise VolatilityModelError(
                "refusal_reasons must be a tuple of non-empty strings"
            )
        if self.available:
            if self.refusal_reasons:
                raise VolatilityModelError("an available forecast cannot carry refusal reasons")
            if (
                self.annualized_volatility_pct is None
                or not math.isfinite(float(self.annualized_volatility_pct))
                or self.annualized_volatility_pct <= 0
            ):
                raise VolatilityModelError(
                    "an available forecast requires positive finite volatility"
                )
            if (
                not isinstance(self.prediction_interval_pct, tuple)
                or len(self.prediction_interval_pct) != 2
            ):
                raise VolatilityModelError("an available forecast requires a two-sided interval")
            lower, upper = self.prediction_interval_pct
            if not all(math.isfinite(float(v)) and v > 0 for v in (lower, upper)):
                raise VolatilityModelError("prediction interval must be positive and finite")
            if lower > self.annualized_volatility_pct or upper < self.annualized_volatility_pct:
                raise VolatilityModelError("prediction interval must contain the point forecast")
            probability = self.probability_above_mandate_ceiling
            if probability is None or not math.isfinite(float(probability)) or not 0 <= probability <= 1:
                raise VolatilityModelError("ceiling probability must be within [0, 1]")
        else:
            if not self.refusal_reasons:
                raise VolatilityModelError("an unavailable forecast must carry a reason")
            if any(
                value is not None
                for value in (
                    self.annualized_volatility_pct,
                    self.prediction_interval_pct,
                    self.probability_above_mandate_ceiling,
                )
            ):
                raise VolatilityModelError(
                    "an unavailable forecast cannot carry numeric predictions"
                )

    @property
    def production_authoritative(self) -> bool:
        """Always False. See ml/contracts.py -- authority can only come from
        a separate, explicit promotion decision that does not exist yet."""
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "subject_key": self.subject_key,
            "horizon_sessions": self.horizon_sessions,
            "as_of_session": self.as_of_session,
            "annualized_volatility_pct": self.annualized_volatility_pct,
            "prediction_interval_pct": (
                list(self.prediction_interval_pct)
                if self.prediction_interval_pct is not None
                else None
            ),
            "probability_above_mandate_ceiling": self.probability_above_mandate_ceiling,
            "model_key": self.model_key,
            "evidence_status": self.evidence_status,
            "available": self.available,
            "refusal_reasons": list(self.refusal_reasons),
            "production_authoritative": self.production_authoritative,
        }


def unavailable_forecast(
    *,
    subject_key: str,
    horizon_sessions: int,
    as_of_session: str,
    model_key: str,
    reasons: Sequence[str],
) -> VolatilityForecast:
    """Doc 3.3: missing/stale/non-finite features produce an unavailable
    prediction, never a default high-confidence one."""
    if not reasons:
        raise VolatilityModelError("an unavailable forecast must carry a reason")
    return VolatilityForecast(
        task="volatility_forecast",
        subject_key=subject_key,
        horizon_sessions=horizon_sessions,
        as_of_session=as_of_session,
        annualized_volatility_pct=None,
        prediction_interval_pct=None,
        probability_above_mandate_ceiling=None,
        model_key=model_key,
        evidence_status="unavailable",
        available=False,
        refusal_reasons=tuple(reasons),
    )


def annualize_pct(daily_volatility_pct: float) -> float:
    """Daily percent std -> annualized percent, sqrt-of-time."""
    if not math.isfinite(daily_volatility_pct) or daily_volatility_pct < 0:
        raise VolatilityModelError("daily_volatility_pct must be non-negative and finite")
    return float(daily_volatility_pct * math.sqrt(252))


def forecast_trailing_baseline(
    daily_returns: pd.Series, *, horizon_sessions: int = PRIMARY_HORIZON_SESSIONS
) -> float | None:
    """Baseline forecast: the trailing realized volatility over a window the
    same length as the horizon being forecast."""
    return trailing_realized_volatility_pct(daily_returns, window=horizon_sessions)


def forecast_ewma_baseline(
    daily_returns: pd.Series, *, halflife: float = 20.0
) -> float | None:
    return ewma_volatility_pct(daily_returns, halflife=halflife)


def build_volatility_training_matrix(
    feature_frame: pd.DataFrame,
    *,
    feature_columns: Sequence[str],
    target_column: str,
) -> tuple[np.ndarray, np.ndarray, tuple[str, ...]]:
    """Extract an (X, y, ordered_feature_names) triple, dropping any row
    with a non-finite feature or target.

    Returns the ORDERED feature names alongside the matrix so a caller can
    record them in a ModelManifest -- ml/contracts.py's
    require_matching_feature_order() then makes a later column-order
    mismatch impossible to miss.
    """
    missing = [c for c in feature_columns if c not in feature_frame.columns]
    if missing:
        raise VolatilityModelError(f"feature frame is missing columns: {missing}")
    if target_column not in feature_frame.columns:
        raise VolatilityModelError(f"feature frame is missing target {target_column!r}")
    ordered = tuple(feature_columns)
    if len(set(ordered)) != len(ordered):
        raise VolatilityModelError("feature_columns contains duplicates")

    subset = feature_frame[list(ordered) + [target_column]].apply(
        pd.to_numeric, errors="coerce"
    ).replace([np.inf, -np.inf], np.nan).dropna()
    if subset.empty:
        raise VolatilityModelError("no rows survive finite-value filtering")
    x = subset[list(ordered)].to_numpy(dtype=float)
    y = subset[target_column].to_numpy(dtype=float)
    return x, y, ordered


def fit_log_volatility_regression(
    x_train: np.ndarray, y_train: np.ndarray, *, alpha: float = 1.0, random_seed: int = 0
):
    """Ridge on log(volatility) (doc 8.2 model #3).

    Targets must be strictly positive -- a zero or negative "volatility"
    is not a real observation and log() of it is undefined, so this refuses
    rather than silently clipping the target into validity.
    """
    from sklearn.linear_model import Ridge

    if (
        isinstance(alpha, bool)
        or not isinstance(alpha, (int, float))
        or not math.isfinite(float(alpha))
        or alpha < 0
    ):
        raise VolatilityModelError("alpha must be a non-negative finite number")

    x_train = np.asarray(x_train, dtype=float)
    y_train = np.asarray(y_train, dtype=float)
    if x_train.ndim != 2 or y_train.ndim != 1 or x_train.shape[0] != y_train.shape[0]:
        raise VolatilityModelError("x_train and y_train must have aligned 2D/1D rows")
    if not np.isfinite(x_train).all() or not np.isfinite(y_train).all():
        raise VolatilityModelError("training data must be finite")
    if x_train.shape[0] < MIN_TRAINING_ROWS:
        raise VolatilityModelError(
            f"need at least {MIN_TRAINING_ROWS} training rows, got {x_train.shape[0]}"
        )
    if np.any(y_train <= 0):
        raise VolatilityModelError("log-volatility target requires strictly positive values")
    model = Ridge(alpha=alpha, random_state=random_seed)
    model.fit(x_train, np.log(y_train))
    return model


def fit_gradient_boosted_volatility(
    x_train: np.ndarray, y_train: np.ndarray, *, random_seed: int = 0, max_iter: int = 200
):
    """HistGradientBoostingRegressor on log volatility (doc 8.2 model #4).

    Doc 8.2 is explicit that this is used "only if it beats the baselines" --
    fitting it is cheap, TRUSTING it is what requires clearing
    ml/evaluation.py's beats_baseline_in_multiple_folds().
    """
    from sklearn.ensemble import HistGradientBoostingRegressor

    if isinstance(max_iter, bool) or not isinstance(max_iter, int) or max_iter < 1:
        raise VolatilityModelError("max_iter must be a positive integer")

    x_train = np.asarray(x_train, dtype=float)
    y_train = np.asarray(y_train, dtype=float)
    if x_train.ndim != 2 or y_train.ndim != 1 or x_train.shape[0] != y_train.shape[0]:
        raise VolatilityModelError("x_train and y_train must have aligned 2D/1D rows")
    if not np.isfinite(x_train).all() or not np.isfinite(y_train).all():
        raise VolatilityModelError("training data must be finite")
    if x_train.shape[0] < MIN_TRAINING_ROWS:
        raise VolatilityModelError(
            f"need at least {MIN_TRAINING_ROWS} training rows, got {x_train.shape[0]}"
        )
    if np.any(y_train <= 0):
        raise VolatilityModelError("log-volatility target requires strictly positive values")
    model = HistGradientBoostingRegressor(
        random_state=random_seed, max_iter=max_iter, early_stopping=False
    )
    model.fit(x_train, np.log(y_train))
    return model


def predict_volatility(model, x: np.ndarray) -> np.ndarray:
    """Exponentiate a log-volatility model's output back to volatility.

    Structurally positive by construction -- no clipping, no max(0, ...)
    patch that would silently mask a model predicting nonsense.
    """
    values = np.asarray(x, dtype=float)
    if values.ndim != 2 or not np.isfinite(values).all():
        raise VolatilityModelError("prediction features must be a finite 2D matrix")
    predictions = np.exp(np.asarray(model.predict(values), dtype=float))
    if predictions.ndim != 1 or not np.isfinite(predictions).all() or np.any(predictions <= 0):
        raise VolatilityModelError("model produced non-positive or non-finite volatility")
    return predictions


def evaluate_volatility_models(
    feature_frame: pd.DataFrame,
    folds: Sequence[Any],
    *,
    feature_columns: Sequence[str],
    target_column: str,
    trailing_baseline_column: str,
    ewma_baseline_column: str,
    random_seed: int = 0,
) -> list[dict[str, Any]]:
    """Fit and score all four doc-8.2 models on each purged walk-forward fold.

    `folds` are ml/splits.py Fold objects. Every model is fit on the fold's
    TRAIN rows only and scored on its untouched VALIDATION rows; nothing here
    ever sees the whole dataset at once, which is the entire point of
    accepting pre-computed folds rather than doing its own splitting.
    """
    required_columns = set(feature_columns) | {
        target_column,
        trailing_baseline_column,
        ewma_baseline_column,
    }
    missing_columns = sorted(required_columns - set(feature_frame.columns))
    if missing_columns:
        raise VolatilityModelError(f"feature frame is missing columns: {missing_columns}")
    results: list[dict[str, Any]] = []
    for fold in folds:
        train_index = list(fold.train_row_indices)
        validation_index = list(fold.validation_row_indices)
        train_frame = feature_frame.iloc[train_index]
        validation_frame = feature_frame.iloc[validation_index]

        metrics: dict[str, Any] = {
            "fold_index": fold.fold_index,
            "train_start": fold.train_start,
            "train_end": fold.train_end,
            "validation_start": fold.validation_start,
            "validation_end": fold.validation_end,
            "train_row_count": len(train_index),
            "validation_row_count": len(validation_index),
            "purged_row_count": fold.purged_row_count,
            "embargoed_row_count": fold.embargoed_row_count,
        }

        comparison_columns = list(dict.fromkeys(
            list(feature_columns)
            + [target_column, trailing_baseline_column, ewma_baseline_column]
        ))
        validation_common = validation_frame[comparison_columns].apply(
            pd.to_numeric, errors="coerce"
        ).replace([np.inf, -np.inf], np.nan).dropna()
        before_positive_filter = len(validation_common)
        positive_columns = [
            target_column, trailing_baseline_column, ewma_baseline_column
        ]
        validation_common = validation_common[
            (validation_common[positive_columns] > 0).all(axis=1)
        ]
        metrics["nonpositive_validation_rows_excluded"] = (
            before_positive_filter - len(validation_common)
        )
        metrics["common_validation_row_count"] = len(validation_common)
        actual = validation_common[target_column].to_numpy(dtype=float)

        for label, column in (
            ("trailing", trailing_baseline_column),
            ("ewma", ewma_baseline_column),
        ):
            predicted = pd.to_numeric(
                validation_common[column], errors="coerce"
            ).to_numpy(dtype=float)
            metrics[f"{label}_qlike"] = qlike_loss(actual, predicted)
            metrics[f"{label}_mae"] = mean_absolute_error(actual, predicted)

        try:
            x_train, y_train, ordered = build_volatility_training_matrix(
                train_frame, feature_columns=feature_columns, target_column=target_column
            )
            if validation_common.empty:
                raise VolatilityModelError(
                    "no common validation rows survive model and baseline requirements"
                )
            x_validation = validation_common[list(feature_columns)].to_numpy(dtype=float)
            y_validation = actual
            metrics["ordered_feature_names"] = list(ordered)

            ridge = fit_log_volatility_regression(
                x_train, y_train, random_seed=random_seed
            )
            ridge_prediction = predict_volatility(ridge, x_validation)
            metrics["ridge_qlike"] = qlike_loss(y_validation, ridge_prediction)
            metrics["ridge_mae"] = mean_absolute_error(y_validation, ridge_prediction)

            boosted = fit_gradient_boosted_volatility(
                x_train, y_train, random_seed=random_seed
            )
            boosted_prediction = predict_volatility(boosted, x_validation)
            metrics["gbm_qlike"] = qlike_loss(y_validation, boosted_prediction)
            metrics["gbm_mae"] = mean_absolute_error(y_validation, boosted_prediction)
            metrics["model_fit_error"] = None
        except VolatilityModelError as error:
            # A fold too thin to fit is recorded as a fold with no ML metrics,
            # not silently skipped -- doc 10.2: "Record unavailable
            # predictions and their reasons; do not log only successes."
            metrics["ridge_qlike"] = None
            metrics["ridge_mae"] = None
            metrics["gbm_qlike"] = None
            metrics["gbm_mae"] = None
            metrics["model_fit_error"] = str(error)

        results.append(metrics)
    return results


def empirical_prediction_interval(
    point_forecast_pct: float,
    residual_log_errors: Sequence[float],
    *,
    coverage: float = 0.90,
) -> tuple[float, float] | None:
    """Interval from the empirical distribution of a model's own past
    log-scale errors, rather than a normal assumption.

    Volatility forecast errors are not symmetric on the raw scale, so a
    +/- k*sigma band would be systematically wrong at the low end (it can go
    negative) and too narrow at the high end -- exactly the tail that
    matters for risk.
    """
    if not 0 < coverage < 1:
        raise VolatilityModelError("coverage must be in (0, 1)")
    if not math.isfinite(point_forecast_pct) or point_forecast_pct <= 0:
        return None
    errors = np.asarray(residual_log_errors, dtype=float)
    errors = errors[np.isfinite(errors)]
    if errors.size < 20:
        return None
    tail = (1.0 - coverage) / 2.0
    low_quantile = float(np.quantile(errors, tail))
    high_quantile = float(np.quantile(errors, 1.0 - tail))
    lower = float(point_forecast_pct * math.exp(low_quantile))
    upper = float(point_forecast_pct * math.exp(high_quantile))
    if not (math.isfinite(lower) and math.isfinite(upper)) or upper < lower:
        return None
    return (round(lower, 6), round(upper, 6))


def probability_above_ceiling(
    point_forecast_pct: float,
    residual_log_errors: Sequence[float],
    *,
    ceiling_pct: float,
) -> float | None:
    """Empirical probability the realized volatility exceeds a mandate
    ceiling, from the same residual distribution as the interval.

    Doc 8.3 lists "calibration for the event 'volatility exceeds mandate
    ceiling'" as a primary metric -- this is the quantity that gets
    calibrated, and doc 16 forbids displaying it as "confidence" until that
    calibration has actually been measured.
    """
    if not math.isfinite(ceiling_pct) or ceiling_pct <= 0:
        raise VolatilityModelError("ceiling_pct must be a positive finite number")
    if not math.isfinite(point_forecast_pct) or point_forecast_pct <= 0:
        return None
    errors = np.asarray(residual_log_errors, dtype=float)
    errors = errors[np.isfinite(errors)]
    if errors.size < 20:
        return None
    implied = point_forecast_pct * np.exp(errors)
    return round(float(np.mean(implied > ceiling_pct)), 6)
