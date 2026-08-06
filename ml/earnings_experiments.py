"""Earnings-gap experiment task for the immutable shared runner (ML-LR-4).

The unit of evidence is one distinct earnings event.  Baselines are formed
from training events first, every candidate sees the same finite validation
events, and all inference is grouped by the canonical Eastern event date.
This module emits research metrics and fitted artifacts only; it has no trade
or promotion authority.
"""
from __future__ import annotations

import dataclasses
import math
import re
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from backtest.engine import bootstrap_edge_significance_by_block
from ml.earnings_gap import (
    MIN_EVENTS_FOR_FIT,
    MIN_TAIL_EVENTS_FOR_FIT,
    fit_gap_magnitude_quantiles,
    fit_gap_threshold_classifier,
)
from ml.earnings_features import EarningsGapForecast
from ml.evaluation import (
    beats_baseline_in_multiple_folds,
    brier_score,
    calibration_curve,
    interval_coverage,
    log_loss,
    mean_absolute_error,
    pinball_loss,
    usable_pair_count,
)
from ml.experiment_contracts import ExperimentSpec
from ml.hashing import hash_payload
from ml.transforms import apply_training_standardizer, fit_training_standardizer

TASK = "earnings_gap_forecast"
BASELINES = (
    "historical_median_absolute_gap",
    "unconditional_frequency",
)
CANDIDATES = (
    "logistic_absolute_threshold",
    "logistic_downside_tail",
    "quantile_absolute_gap",
    "hist_gradient_boosting_absolute_threshold",
)
REQUIRED_EVENT_COLUMNS = (
    "event_id",
    "event_date",
    "industry",
    "release_timing",
    "pre_event_volatility_pct",
)
SLICE_COLUMNS = (
    "ticker",
    "industry",
    "year",
    "volatility_regime",
    "release_timing",
)
_PARAMETER_KEYS = frozenset(
    {
        "absolute_gap_threshold_pct",
        "downside_gap_threshold_pct",
        "classification_probability_threshold",
        "quantiles",
        "minimum_group_baseline_events",
        "confirmation_minimum_distinct_events",
        "confirmation_minimum_upside_tail_events",
        "confirmation_minimum_downside_tail_events",
        "confirmation_sample_justification",
    }
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class EarningsExperimentError(ValueError):
    """An earnings experiment is not completely preregistered or auditable."""


@dataclasses.dataclass(frozen=True)
class EarningsExperimentConfig:
    absolute_gap_threshold_pct: float
    downside_gap_threshold_pct: float
    classification_probability_threshold: float
    quantiles: tuple[float, ...]
    minimum_group_baseline_events: int
    confirmation_minimum_distinct_events: int
    confirmation_minimum_upside_tail_events: int
    confirmation_minimum_downside_tail_events: int
    confirmation_sample_justification: str


@dataclasses.dataclass(frozen=True)
class FittedEarningsModel:
    """Duck-compatible with the shared runner's artifact writer."""

    estimator: Any
    standardizer: Any
    algorithm: str
    hyperparameters: Mapping[str, Any]
    training_start: str
    training_end: str


def build_typed_forecast(
    spec: ExperimentSpec,
    event: Mapping[str, Any],
    model_bundles: Mapping[str, Mapping[str, Any]],
    artifact_hashes: Mapping[str, str],
    *,
    target_available_at: str,
    baseline_median_absolute_gap_pct: float,
    event_support: Mapping[str, Any],
    calibration_status: str,
    evidence_status: str,
) -> EarningsGapForecast:
    """Create the typed forecast from hash-verified persisted bundles.

    Loading and hash verification remain the responsibility of
    :func:`ml.artifacts.load_model_artifact`; this function refuses an
    incomplete or feature-order-mismatched bundle set.  The single artifact
    hash in the output is the canonical digest of the complete frozen model
    set, so the forecast is bound to the exact evaluated run rather than
    ambiguously naming only one component.
    """
    config = validate_earnings_spec(spec)
    if set(model_bundles) != set(CANDIDATES):
        raise EarningsExperimentError(
            f"model_bundles must contain exactly the frozen candidates {CANDIDATES!r}"
        )
    if set(artifact_hashes) != set(CANDIDATES):
        raise EarningsExperimentError(
            f"artifact_hashes must contain exactly the frozen candidates {CANDIDATES!r}"
        )
    malformed_hashes = [
        candidate
        for candidate, digest in artifact_hashes.items()
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None
    ]
    if malformed_hashes:
        raise EarningsExperimentError(
            f"artifact_hashes contains malformed SHA-256 values: {sorted(malformed_hashes)}"
        )
    required_event = {
        "event_id", "ticker", "announced_at_utc", "release_timing", "as_of_session",
    }
    missing_event = required_event - set(event)
    if missing_event:
        raise EarningsExperimentError(
            f"event is missing typed forecast field(s): {sorted(missing_event)}"
        )
    try:
        raw_features = np.asarray(
            [float(event[name]) for name in spec.ordered_feature_names], dtype=float
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise EarningsExperimentError(
            "event does not contain every ordered finite model feature"
        ) from exc
    if not np.isfinite(raw_features).all():
        raise EarningsExperimentError("event model features must be finite")

    def matrix_for(candidate: str) -> tuple[np.ndarray, Any]:
        bundle = model_bundles[candidate]
        if not isinstance(bundle, Mapping):
            raise EarningsExperimentError(f"bundle {candidate!r} must be a mapping")
        if tuple(bundle.get("ordered_feature_names", ())) != spec.ordered_feature_names:
            raise EarningsExperimentError(
                f"bundle {candidate!r} feature order does not match the spec"
            )
        standardizer = bundle.get("standardizer")
        if not isinstance(standardizer, Mapping):
            raise EarningsExperimentError(f"bundle {candidate!r} has no standardizer")
        means = standardizer.get("means")
        scales = standardizer.get("scales")
        if not isinstance(means, Mapping) or not isinstance(scales, Mapping):
            raise EarningsExperimentError(
                f"bundle {candidate!r} standardizer is incomplete"
            )
        try:
            mean = np.asarray([float(means[name]) for name in spec.ordered_feature_names])
            scale = np.asarray([float(scales[name]) for name in spec.ordered_feature_names])
        except (KeyError, TypeError, ValueError) as exc:
            raise EarningsExperimentError(
                f"bundle {candidate!r} standardizer does not match feature order"
            ) from exc
        if not np.isfinite(mean).all() or not np.isfinite(scale).all() or np.any(scale <= 0):
            raise EarningsExperimentError(
                f"bundle {candidate!r} standardizer is not finite and positive-scaled"
            )
        estimator = bundle.get("estimator")
        if estimator is None:
            raise EarningsExperimentError(f"bundle {candidate!r} has no estimator")
        return ((raw_features - mean) / scale).reshape(1, -1), estimator

    absolute_x, absolute_model = matrix_for(CANDIDATES[0])
    downside_x, downside_model = matrix_for(CANDIDATES[1])
    quantile_x, quantile_models = matrix_for(CANDIDATES[2])
    # Validate the boosted bundle even though the typed output deliberately
    # reports the simple logistic probability. The boosted model remains an
    # evaluated challenger, not a silent replacement for the interpretable
    # preregistered classifier.
    matrix_for(CANDIDATES[3])
    try:
        probability_absolute = float(absolute_model.predict_proba(absolute_x)[0, 1])
        probability_downside = float(downside_model.predict_proba(downside_x)[0, 1])
        lower = float(
            np.clip(quantile_models[config.quantiles[0]].predict(quantile_x)[0], 0.0, None)
        )
        upper = float(
            np.clip(quantile_models[config.quantiles[-1]].predict(quantile_x)[0], 0.0, None)
        )
    except (AttributeError, KeyError, TypeError, ValueError, IndexError) as exc:
        raise EarningsExperimentError("persisted earnings bundle cannot produce a forecast") from exc

    snapshot_hash = hash_payload(
        {
            "event_id": event["event_id"],
            "as_of_session": event["as_of_session"],
            "ordered_features": {
                name: float(event[name]) for name in spec.ordered_feature_names
            },
        }
    )
    return EarningsGapForecast(
        event_id=str(event["event_id"]),
        ticker=str(event["ticker"]),
        announced_at_utc=str(event["announced_at_utc"]),
        release_timing=str(event["release_timing"]),
        as_of_session=str(event["as_of_session"]),
        target_available_at=target_available_at,
        absolute_gap_interval_pct=(min(lower, upper), max(lower, upper)),
        probability_above_absolute_threshold=probability_absolute,
        probability_below_downside_threshold=probability_downside,
        absolute_threshold_pct=config.absolute_gap_threshold_pct,
        downside_threshold_pct=config.downside_gap_threshold_pct,
        baseline_median_absolute_gap_pct=baseline_median_absolute_gap_pct,
        calibration_status=calibration_status,
        event_support=event_support,
        model_key=f"{spec.experiment_id}:{spec.spec_hash}",
        artifact_hash=hash_payload(dict(sorted(artifact_hashes.items()))),
        feature_snapshot_hash=snapshot_hash,
        evidence_status=evidence_status,
        available=True,
    )


def validate_earnings_spec(spec: ExperimentSpec) -> EarningsExperimentConfig:
    """Require the complete model order and every behavior-changing value."""
    if spec.task != TASK:
        raise EarningsExperimentError(f"expected task {TASK!r}, got {spec.task!r}")
    if spec.candidate_models != CANDIDATES:
        raise EarningsExperimentError(
            "earnings candidate_models must use the complete frozen order: "
            f"{CANDIDATES!r}"
        )
    if spec.frozen_baselines != BASELINES:
        raise EarningsExperimentError(
            f"earnings frozen_baselines must be exactly {BASELINES!r}"
        )
    if spec.baseline_columns:
        raise EarningsExperimentError(
            "earnings baselines are fitted from training events; baseline_columns must be empty"
        )
    parameters = dict(spec.task_parameters)
    missing = _PARAMETER_KEYS - set(parameters)
    unknown = set(parameters) - _PARAMETER_KEYS
    if missing or unknown:
        raise EarningsExperimentError(
            f"earnings task_parameters mismatch; missing={sorted(missing)}, "
            f"unknown={sorted(unknown)}"
        )

    def finite_number(name: str) -> float:
        value = parameters[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise EarningsExperimentError(f"task_parameters.{name} must be finite")
        return float(value)

    absolute = finite_number("absolute_gap_threshold_pct")
    downside = finite_number("downside_gap_threshold_pct")
    probability = finite_number("classification_probability_threshold")
    if absolute <= 0:
        raise EarningsExperimentError("absolute_gap_threshold_pct must be positive")
    if downside >= 0:
        raise EarningsExperimentError("downside_gap_threshold_pct must be negative")
    if not 0 < probability < 1:
        raise EarningsExperimentError(
            "classification_probability_threshold must be within (0, 1)"
        )
    raw_quantiles = parameters["quantiles"]
    if not isinstance(raw_quantiles, (list, tuple)) or len(raw_quantiles) < 3:
        raise EarningsExperimentError("quantiles must contain at least lower, median, upper")
    quantiles = tuple(float(value) for value in raw_quantiles)
    if (
        any(not math.isfinite(value) or not 0 < value < 1 for value in quantiles)
        or tuple(sorted(quantiles)) != quantiles
        or len(set(quantiles)) != len(quantiles)
        or 0.5 not in quantiles
    ):
        raise EarningsExperimentError(
            "quantiles must be unique, strictly increasing values in (0, 1) including 0.5"
        )
    group_minimum = parameters["minimum_group_baseline_events"]
    if (
        isinstance(group_minimum, bool)
        or not isinstance(group_minimum, int)
        or group_minimum < 2
    ):
        raise EarningsExperimentError("minimum_group_baseline_events must be an integer >= 2")
    integer_minima = {
        "confirmation_minimum_distinct_events": MIN_EVENTS_FOR_FIT,
        "confirmation_minimum_upside_tail_events": MIN_TAIL_EVENTS_FOR_FIT,
        "confirmation_minimum_downside_tail_events": MIN_TAIL_EVENTS_FOR_FIT,
    }
    validated_minima: dict[str, int] = {}
    for name, floor in integer_minima.items():
        value = parameters[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < floor:
            raise EarningsExperimentError(
                f"{name} must be an integer >= the software fit floor ({floor})"
            )
        validated_minima[name] = value
    justification = parameters["confirmation_sample_justification"]
    if not isinstance(justification, str) or not justification.strip():
        raise EarningsExperimentError(
            "confirmation_sample_justification must be a non-empty string"
        )
    normalized_justification = justification.strip().lower().replace("-", " ")
    if "power" not in normalized_justification and "effect size" not in normalized_justification:
        raise EarningsExperimentError(
            "confirmation_sample_justification must state a power or effect-size basis"
        )
    return EarningsExperimentConfig(
        absolute_gap_threshold_pct=absolute,
        downside_gap_threshold_pct=downside,
        classification_probability_threshold=probability,
        quantiles=quantiles,
        minimum_group_baseline_events=group_minimum,
        confirmation_minimum_distinct_events=validated_minima[
            "confirmation_minimum_distinct_events"
        ],
        confirmation_minimum_upside_tail_events=validated_minima[
            "confirmation_minimum_upside_tail_events"
        ],
        confirmation_minimum_downside_tail_events=validated_minima[
            "confirmation_minimum_downside_tail_events"
        ],
        confirmation_sample_justification=justification.strip(),
    )


def _validate_event_rows(joined: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_EVENT_COLUMNS if column not in joined]
    if missing:
        raise EarningsExperimentError(
            f"earnings dataset is missing event column(s): {missing}"
        )
    if joined["event_id"].isna().any() or joined["event_id"].duplicated().any():
        raise EarningsExperimentError(
            "event_id must be present and globally unique; repeated rows are not evidence"
        )
    parsed = pd.to_datetime(joined["event_date"], format="%Y-%m-%d", errors="coerce")
    if parsed.isna().any() or not parsed.dt.strftime("%Y-%m-%d").equals(joined["event_date"]):
        raise EarningsExperimentError("event_date must use canonical YYYY-MM-DD format")
    if joined["industry"].isna().any() or (joined["industry"].astype(str).str.strip() == "").any():
        raise EarningsExperimentError("industry must be present for every event")
    invalid_timing = set(joined["release_timing"].dropna()) - {"after_close", "before_open"}
    if invalid_timing or joined["release_timing"].isna().any():
        raise EarningsExperimentError(
            "primary earnings experiments accept only before_open/after_close events; "
            f"invalid={sorted(invalid_timing)}"
        )


def _hierarchical_median_baseline(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    *,
    target_column: str,
    minimum_group_events: int,
) -> np.ndarray:
    magnitude = train[target_column].abs()
    ticker_groups = train.assign(_magnitude=magnitude).groupby("ticker")["_magnitude"]
    industry_groups = train.assign(_magnitude=magnitude).groupby("industry")["_magnitude"]
    ticker_median = ticker_groups.median()
    ticker_count = ticker_groups.count()
    industry_median = industry_groups.median()
    industry_count = industry_groups.count()
    global_median = float(magnitude.median())
    predictions: list[float] = []
    for row in validation.itertuples():
        if ticker_count.get(row.ticker, 0) >= minimum_group_events:
            predictions.append(float(ticker_median[row.ticker]))
        elif industry_count.get(row.industry, 0) >= minimum_group_events:
            predictions.append(float(industry_median[row.industry]))
        else:
            predictions.append(global_median)
    return np.asarray(predictions, dtype=float)


def _classification_metrics(
    actual: np.ndarray,
    probability: np.ndarray,
    *,
    threshold: float,
    bins: int,
) -> dict[str, Any]:
    predicted = probability >= threshold
    positives = actual == 1
    true_positive = int(np.sum(predicted & positives))
    predicted_positive = int(np.sum(predicted))
    actual_positive = int(np.sum(positives))
    curve = calibration_curve(actual, probability, n_bins=bins)
    calibration_error = sum(
        row["count"] * abs(row["mean_predicted"] - row["observed_frequency"])
        for row in curve
        if row["count"]
    ) / len(actual)
    return {
        "brier_score": brier_score(actual, probability),
        "log_loss": log_loss(actual, probability),
        "probability_threshold": threshold,
        "precision": true_positive / predicted_positive if predicted_positive else None,
        "recall": true_positive / actual_positive if actual_positive else None,
        "calibration_error": float(calibration_error),
        "calibration_curve": curve,
    }


def _support(
    gaps: np.ndarray,
    tickers: Sequence[str],
    absolute_threshold: float,
    downside_threshold: float,
) -> dict[str, Any]:
    upside = int(np.sum(gaps >= absolute_threshold))
    downside = int(np.sum(gaps <= downside_threshold))
    reasons: list[str] = []
    if len(gaps) < MIN_EVENTS_FOR_FIT:
        reasons.append(f"only {len(gaps)} events; {MIN_EVENTS_FOR_FIT} required")
    if upside < MIN_TAIL_EVENTS_FOR_FIT:
        reasons.append(f"only {upside} upside-tail events; {MIN_TAIL_EVENTS_FOR_FIT} required")
    if downside < MIN_TAIL_EVENTS_FOR_FIT:
        reasons.append(f"only {downside} downside-tail events; {MIN_TAIL_EVENTS_FOR_FIT} required")
    return {
        "distinct_events": int(len(gaps)),
        "distinct_tickers": int(len(set(tickers))),
        "upside_tail_events": upside,
        "downside_tail_events": downside,
        "fit_refusal_minimum_events": MIN_EVENTS_FOR_FIT,
        "fit_refusal_minimum_per_tail": MIN_TAIL_EVENTS_FOR_FIT,
        "sufficient_for_fit": not reasons,
        "insufficiency_reasons": reasons,
        "fit_minimum_is_not_a_promotion_threshold": True,
    }


def _slice_metrics(frame: pd.DataFrame, candidate: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    classifier = candidate != "quantile_absolute_gap"
    actual_column = (
        "actual_downside_tail"
        if candidate == "logistic_downside_tail"
        else "actual_absolute_tail"
    )
    prediction_column = f"prediction_{candidate}"
    for dimension in SLICE_COLUMNS:
        groups: dict[str, Any] = {}
        for value, group in frame.groupby(dimension, dropna=False, sort=True):
            actual = group[actual_column if classifier else "absolute_gap"].to_numpy(float)
            predicted = group[prediction_column].to_numpy(float)
            metric = (
                brier_score(actual, predicted)
                if classifier
                else mean_absolute_error(actual, predicted)
            )
            # event_count is the slice's size; scored_event_count is what the
            # metric actually used. brier_score/mean_absolute_error drop
            # non-finite pairs, so reporting only the former lets a slice the
            # model mostly FAILED to predict display a strong score over its
            # few easy survivors. Match the fold-summary discipline
            # (evaluated_validation_row_count), not monitoring_reports' date
            # sufficiency counts — those answer a different question.
            groups[str(value)] = {
                "event_count": int(len(group)),
                "scored_event_count": usable_pair_count(actual, predicted),
                "primary_metric": metric,
            }
        result[dimension] = groups
    return result


def run_earnings_task(
    spec: ExperimentSpec,
    joined: pd.DataFrame,
    folds: Sequence[Any],
    *,
    feature_columns: Sequence[str],
    target_column: str,
) -> tuple[list[dict[str, Any]], dict[str, FittedEarningsModel], dict[str, Any]]:
    """Fit/evaluate the frozen earnings sequence on event-date folds."""
    config = validate_earnings_spec(spec)
    _validate_event_rows(joined)
    fold_metrics: list[dict[str, Any]] = []
    fitted_models: dict[str, FittedEarningsModel] = {}
    out_of_fold: list[pd.DataFrame] = []

    for fold in folds:
        train = joined.iloc[list(fold.train_row_indices)].copy()
        validation = joined.iloc[list(fold.validation_row_indices)].copy()
        numeric_columns = list(dict.fromkeys([*feature_columns, target_column]))
        train_numeric = train[numeric_columns].apply(pd.to_numeric, errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        ).dropna()
        validation_numeric = validation[numeric_columns].apply(
            pd.to_numeric, errors="coerce"
        ).replace([np.inf, -np.inf], np.nan).dropna()
        train_eval = train.loc[train_numeric.index].copy()
        validation_eval = validation.loc[validation_numeric.index].copy()
        train_eval[numeric_columns] = train_numeric
        validation_eval[numeric_columns] = validation_numeric

        train_gaps = train_eval[target_column].to_numpy(dtype=float)
        validation_gaps = validation_eval[target_column].to_numpy(dtype=float)
        metrics: dict[str, Any] = {
            "fold_index": fold.fold_index,
            "train_start": fold.train_start,
            "train_end": fold.train_end,
            "validation_start": fold.validation_start,
            "validation_end": fold.validation_end,
            "train_row_count": len(train),
            "validation_row_count": len(validation),
            "evaluated_validation_row_count": len(validation_eval),
            "purged_row_count": fold.purged_row_count,
            "embargoed_row_count": fold.embargoed_row_count,
            "train_support": _support(
                train_gaps,
                train_eval["ticker"],
                config.absolute_gap_threshold_pct,
                config.downside_gap_threshold_pct,
            ),
            "validation_support": _support(
                validation_gaps,
                validation_eval["ticker"],
                config.absolute_gap_threshold_pct,
                config.downside_gap_threshold_pct,
            ),
        }
        if train_eval.empty or validation_eval.empty:
            metrics["fit_error"] = "no rows survive the common finite-event filter"
            fold_metrics.append(metrics)
            continue

        # Frozen baselines are computed before any candidate is fit.
        historical = _hierarchical_median_baseline(
            train_eval,
            validation_eval,
            target_column=target_column,
            minimum_group_events=config.minimum_group_baseline_events,
        )
        actual_absolute = np.abs(validation_gaps)
        actual_absolute_tail = (
            actual_absolute >= config.absolute_gap_threshold_pct
        ).astype(float)
        actual_downside = (
            validation_gaps <= config.downside_gap_threshold_pct
        ).astype(float)
        unconditional_absolute = np.full(
            len(validation_eval),
            float(np.mean(np.abs(train_gaps) >= config.absolute_gap_threshold_pct)),
        )
        unconditional_downside = np.full(
            len(validation_eval),
            float(np.mean(train_gaps <= config.downside_gap_threshold_pct)),
        )
        metrics["historical_median_absolute_gap_mae"] = mean_absolute_error(
            actual_absolute, historical
        )
        metrics["unconditional_absolute_brier"] = brier_score(
            actual_absolute_tail, unconditional_absolute
        )
        metrics["unconditional_absolute_log_loss"] = log_loss(
            actual_absolute_tail, unconditional_absolute
        )
        metrics["unconditional_downside_brier"] = brier_score(
            actual_downside, unconditional_downside
        )
        metrics["unconditional_downside_log_loss"] = log_loss(
            actual_downside, unconditional_downside
        )
        metrics["baseline_evaluated_event_count"] = len(validation_eval)

        if not metrics["train_support"]["sufficient_for_fit"]:
            metrics["fit_error"] = "; ".join(
                metrics["train_support"]["insufficiency_reasons"]
            )
            fold_metrics.append(metrics)
            continue

        standardizer = fit_training_standardizer(
            joined,
            list(feature_columns),
            train_row_indices=[int(index) for index in train_eval.index],
        )
        transformed = apply_training_standardizer(joined, standardizer)
        standardized = [f"{name}__standardized" for name in feature_columns]
        x_train = transformed.loc[train_eval.index, standardized].to_numpy(float)
        x_validation = transformed.loc[validation_eval.index, standardized].to_numpy(float)
        absolute_train = np.abs(train_gaps)
        y_absolute = (absolute_train >= config.absolute_gap_threshold_pct).astype(float)
        y_downside = (train_gaps <= config.downside_gap_threshold_pct).astype(float)
        predictions: dict[str, np.ndarray] = {}
        try:
            # The sequence is intentional and mirrors plan 10.2 exactly.
            absolute_model = fit_gap_threshold_classifier(
                x_train, y_absolute, random_seed=spec.random_seed
            )
            predictions[CANDIDATES[0]] = absolute_model.predict_proba(x_validation)[:, 1]
            downside_model = fit_gap_threshold_classifier(
                x_train, y_downside, random_seed=spec.random_seed
            )
            predictions[CANDIDATES[1]] = downside_model.predict_proba(x_validation)[:, 1]
            quantile_models = fit_gap_magnitude_quantiles(
                x_train,
                absolute_train,
                quantiles=config.quantiles,
                random_seed=spec.random_seed,
            )
            quantile_predictions = {
                quantile: np.clip(model.predict(x_validation), 0.0, None)
                for quantile, model in quantile_models.items()
            }
            predictions[CANDIDATES[2]] = quantile_predictions[0.5]

            from sklearn.ensemble import HistGradientBoostingClassifier

            boosted_model = HistGradientBoostingClassifier(
                max_iter=200, early_stopping=False, random_state=spec.random_seed
            )
            boosted_model.fit(x_train, y_absolute)
            predictions[CANDIDATES[3]] = boosted_model.predict_proba(x_validation)[:, 1]
        except Exception as exc:
            metrics["fit_error"] = str(exc)
            fold_metrics.append(metrics)
            continue

        for candidate in (CANDIDATES[0], CANDIDATES[3]):
            candidate_metrics = _classification_metrics(
                actual_absolute_tail,
                predictions[candidate],
                threshold=config.classification_probability_threshold,
                bins=spec.research_gate.required_calibration_bins,
            )
            metrics[f"{candidate}_brier"] = candidate_metrics["brier_score"]
            metrics[f"{candidate}_log_loss"] = candidate_metrics["log_loss"]
            metrics[f"{candidate}_precision"] = candidate_metrics["precision"]
            metrics[f"{candidate}_recall"] = candidate_metrics["recall"]
            metrics[f"{candidate}_calibration_error"] = candidate_metrics[
                "calibration_error"
            ]
        downside_metrics = _classification_metrics(
            actual_downside,
            predictions[CANDIDATES[1]],
            threshold=config.classification_probability_threshold,
            bins=spec.research_gate.required_calibration_bins,
        )
        for name in ("brier_score", "log_loss", "precision", "recall", "calibration_error"):
            short = "brier" if name == "brier_score" else name
            metrics[f"{CANDIDATES[1]}_{short}"] = downside_metrics[name]

        for quantile, values in quantile_predictions.items():
            metrics[f"quantile_absolute_gap_pinball_{quantile:g}"] = pinball_loss(
                actual_absolute, values, quantile=quantile
            )
        lower = quantile_predictions[config.quantiles[0]]
        upper = quantile_predictions[config.quantiles[-1]]
        metrics["quantile_absolute_gap_interval_crossings"] = int(np.sum(lower > upper))
        metrics["quantile_absolute_gap_interval_coverage"] = interval_coverage(
            actual_absolute, np.minimum(lower, upper), np.maximum(lower, upper)
        )
        metrics["quantile_absolute_gap_mae"] = mean_absolute_error(
            actual_absolute, predictions[CANDIDATES[2]]
        )
        metrics["candidate_evaluated_event_count"] = len(validation_eval)
        metrics["fit_error"] = None

        validation_eval["absolute_gap"] = actual_absolute
        validation_eval["actual_absolute_tail"] = actual_absolute_tail
        validation_eval["actual_downside_tail"] = actual_downside
        validation_eval["baseline_historical_median"] = historical
        validation_eval["baseline_unconditional_absolute"] = unconditional_absolute
        validation_eval["baseline_unconditional_downside"] = unconditional_downside
        for candidate, values in predictions.items():
            validation_eval[f"prediction_{candidate}"] = values
        for quantile, values in quantile_predictions.items():
            validation_eval[f"prediction_quantile_absolute_gap_q_{quantile:g}"] = values
        validation_eval["year"] = validation_eval["event_date"].str[:4]
        volatility_cutoff = float(train_eval["pre_event_volatility_pct"].median())
        validation_eval["volatility_regime"] = np.where(
            validation_eval["pre_event_volatility_pct"] >= volatility_cutoff,
            "high",
            "low",
        )
        out_of_fold.append(validation_eval.assign(fold_index=fold.fold_index))

        if fold.fold_index == folds[-1].fold_index:
            definitions = (
                (
                    CANDIDATES[0], absolute_model, type(absolute_model).__name__,
                    {"max_iter": 1000},
                ),
                (
                    CANDIDATES[1], downside_model, type(downside_model).__name__,
                    {"max_iter": 1000},
                ),
                (
                    CANDIDATES[2],
                    quantile_models,
                    "GradientBoostingRegressorQuantiles",
                    {
                        "quantiles": list(config.quantiles),
                        "loss": "quantile",
                        "n_estimators": 100,
                    },
                ),
                (
                    CANDIDATES[3],
                    boosted_model,
                    type(boosted_model).__name__,
                    {"max_iter": 200, "early_stopping": False},
                ),
            )
            for candidate, estimator, algorithm, hyperparameters in definitions:
                fitted_models[candidate] = FittedEarningsModel(
                    estimator=estimator,
                    standardizer=standardizer,
                    algorithm=algorithm,
                    hyperparameters=hyperparameters,
                    training_start=standardizer.training_start,
                    training_end=standardizer.training_end,
                )
        fold_metrics.append(metrics)

    combined = pd.concat(out_of_fold, ignore_index=True) if out_of_fold else pd.DataFrame()
    aggregate: dict[str, Any] = {}
    if combined.empty:
        confirmation_sample_gate: dict[str, Any] = {
            "distinct_events": 0,
            "upside_tail_events": 0,
            "downside_tail_events": 0,
        }
    else:
        combined_gaps = combined[target_column].to_numpy(float)
        confirmation_sample_gate = {
            "distinct_events": int(combined["event_id"].nunique()),
            "upside_tail_events": int(
                np.sum(combined_gaps >= config.absolute_gap_threshold_pct)
            ),
            "downside_tail_events": int(
                np.sum(combined_gaps <= config.downside_gap_threshold_pct)
            ),
        }
    confirmation_sample_gate.update(
        {
            "minimum_distinct_events": config.confirmation_minimum_distinct_events,
            "minimum_upside_tail_events": (
                config.confirmation_minimum_upside_tail_events
            ),
            "minimum_downside_tail_events": (
                config.confirmation_minimum_downside_tail_events
            ),
            "sample_justification": config.confirmation_sample_justification,
        }
    )
    confirmation_sample_gate["passes"] = bool(
        confirmation_sample_gate["distinct_events"]
        >= config.confirmation_minimum_distinct_events
        and confirmation_sample_gate["upside_tail_events"]
        >= config.confirmation_minimum_upside_tail_events
        and confirmation_sample_gate["downside_tail_events"]
        >= config.confirmation_minimum_downside_tail_events
    )
    comparisons = {
        CANDIDATES[0]: ("brier", "unconditional_absolute_brier"),
        CANDIDATES[1]: ("brier", "unconditional_downside_brier"),
        CANDIDATES[2]: ("mae", "historical_median_absolute_gap_mae"),
        CANDIDATES[3]: ("brier", "unconditional_absolute_brier"),
    }
    for candidate in CANDIDATES:
        metric_suffix, baseline_key = comparisons[candidate]
        candidate_key = f"{candidate}_{metric_suffix}"
        fold_gate = beats_baseline_in_multiple_folds(
            fold_metrics,
            candidate_key=candidate_key,
            baseline_key=baseline_key,
            minimum_folds=spec.research_gate.minimum_folds_won,
        )
        if combined.empty or f"prediction_{candidate}" not in combined:
            aggregate[candidate] = {
                **fold_gate,
                "block_significance": {},
                "confirmation_sample_gate": dict(confirmation_sample_gate),
            }
            continue
        if candidate == CANDIDATES[2]:
            point_edge = (
                np.abs(combined["absolute_gap"] - combined["baseline_historical_median"])
                - np.abs(combined["absolute_gap"] - combined[f"prediction_{candidate}"])
            )
        else:
            actual_column = (
                "actual_downside_tail" if candidate == CANDIDATES[1]
                else "actual_absolute_tail"
            )
            baseline_column = (
                "baseline_unconditional_downside" if candidate == CANDIDATES[1]
                else "baseline_unconditional_absolute"
            )
            point_edge = (
                np.square(combined[baseline_column] - combined[actual_column])
                - np.square(combined[f"prediction_{candidate}"] - combined[actual_column])
            )
        significance = {
            str(block): bootstrap_edge_significance_by_block(
                pd.Series(point_edge),
                combined["event_date"],
                block_length=block,
                seed=spec.random_seed,
            )
            for block in spec.research_gate.block_lengths
        }
        aggregate[candidate] = {
            **fold_gate,
            "block_significance": significance,
            "distinct_events": int(combined["event_id"].nunique()),
            "distinct_tickers": int(combined["ticker"].nunique()),
            "failure_slices": _slice_metrics(combined, candidate),
            "confirmation_sample_gate": dict(confirmation_sample_gate),
        }
        if spec.mode == "confirmation" and not confirmation_sample_gate["passes"]:
            aggregate[candidate]["passes"] = False
        if candidate == CANDIDATES[2]:
            lower_column = (
                f"prediction_quantile_absolute_gap_q_{config.quantiles[0]:g}"
            )
            upper_column = (
                f"prediction_quantile_absolute_gap_q_{config.quantiles[-1]:g}"
            )
            lower = combined[lower_column].to_numpy(float)
            upper = combined[upper_column].to_numpy(float)
            aggregate[candidate].update(
                {
                    "mean_absolute_error": mean_absolute_error(
                        combined["absolute_gap"], combined[f"prediction_{candidate}"]
                    ),
                    "baseline_mean_absolute_error": mean_absolute_error(
                        combined["absolute_gap"], combined["baseline_historical_median"]
                    ),
                    "pinball_loss": {
                        str(quantile): pinball_loss(
                            combined["absolute_gap"],
                            combined[f"prediction_quantile_absolute_gap_q_{quantile:g}"],
                            quantile=quantile,
                        )
                        for quantile in config.quantiles
                    },
                    "interval_coverage": interval_coverage(
                        combined["absolute_gap"],
                        np.minimum(lower, upper),
                        np.maximum(lower, upper),
                    ),
                    "interval_crossings": int(np.sum(lower > upper)),
                }
            )
        else:
            actual_column = (
                "actual_downside_tail" if candidate == CANDIDATES[1]
                else "actual_absolute_tail"
            )
            baseline_column = (
                "baseline_unconditional_downside" if candidate == CANDIDATES[1]
                else "baseline_unconditional_absolute"
            )
            aggregate[candidate]["calibration"] = _classification_metrics(
                combined[actual_column].to_numpy(float),
                combined[f"prediction_{candidate}"].to_numpy(float),
                threshold=config.classification_probability_threshold,
                bins=spec.research_gate.required_calibration_bins,
            )
            aggregate[candidate]["baseline_brier_score"] = brier_score(
                combined[actual_column], combined[baseline_column]
            )
    return fold_metrics, fitted_models, aggregate
