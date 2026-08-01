"""ML-LR-3 sections 9.4/9.5: volatility evaluation completion and the typed
shadow forecast.

The single most leakage-prone piece here is the prediction interval.
`expanding_out_of_fold_intervals()` builds fold k's interval from residuals
observed in folds < k ONLY. Using the fold's own residuals -- the obvious
implementation -- calibrates the interval on the very outcomes it is being
scored against, which produces near-perfect coverage that collapses the
moment the model meets a session it has not already seen. Plan 9.6 states
the rule directly: "intervals use only residuals available before the
prediction date."

Everything else here is reporting rather than judgment: slices, coverage,
calibration, and warning behavior are computed and returned, and the
preregistered gate in ml/experiments.py decides what they mean. In
particular a probability is never labeled "confidence" until its
calibration has actually cleared that gate (plan 9.5, strategy doc 16).
"""
from __future__ import annotations

import dataclasses
import math
import re
from datetime import datetime
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from ml.evaluation import (
    EvaluationError,
    brier_score,
    calibration_curve,
    interval_coverage,
    log_loss,
    mean_absolute_error,
    qlike_loss,
)

TRADING_SESSIONS_PER_YEAR = 252
MIN_RESIDUALS_FOR_INTERVAL = 20
MIN_EVENTS_FOR_CALIBRATION = 30
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NON_AUTHORITATIVE_EVIDENCE = frozenset(
    {"exploratory", "promising_unconfirmed", "rejected", "unavailable"}
)


class VolatilityEvaluationError(ValueError):
    """Inputs cannot support a trustworthy volatility evaluation."""


class CalibrationStatus:
    """Whether a threshold probability may be presented as calibrated.

    Deliberately three states, not a boolean. "not measured" and "measured
    and failed" are different epistemic situations, and collapsing them
    would let an unmeasured probability inherit the benefit of the doubt.
    """

    NOT_MEASURED = "not_measured"
    EXPERIMENTAL = "experimental"
    CALIBRATED = "calibrated"

    ALL = (NOT_MEASURED, EXPERIMENTAL, CALIBRATED)


# --- prediction intervals ---------------------------------------------------


def expanding_out_of_fold_intervals(
    fold_predictions: Sequence[Mapping[str, Any]],
    *,
    coverage: float = 0.90,
    minimum_residuals: int = MIN_RESIDUALS_FOR_INTERVAL,
) -> list[dict[str, Any]]:
    """Per-fold intervals built ONLY from earlier folds' residuals.

    `fold_predictions` is an ordered sequence of per-fold mappings with
    "fold_index", "actual", and "predicted" arrays. Fold 0 necessarily has
    no prior residuals and therefore gets NO interval -- reported as
    unavailable rather than silently borrowing later data, which is exactly
    the leak this function exists to prevent.

    Residuals are on the LOG scale because volatility is bounded below by
    zero and right-skewed: a symmetric +/-k*sigma band on the raw scale
    would extend below zero at the low end and be too narrow in the upper
    tail, which is the tail that matters for a risk forecast.
    """
    if not 0 < coverage < 1:
        raise VolatilityEvaluationError("coverage must be in (0, 1)")

    results: list[dict[str, Any]] = []
    prior_residuals: list[float] = []
    tail = (1.0 - coverage) / 2.0

    for fold in fold_predictions:
        actual = np.asarray(fold["actual"], dtype=float)
        predicted = np.asarray(fold["predicted"], dtype=float)
        if actual.shape != predicted.shape:
            raise VolatilityEvaluationError("actual and predicted must align")

        usable = np.isfinite(actual) & np.isfinite(predicted) & (actual > 0) & (predicted > 0)
        entry: dict[str, Any] = {
            "fold_index": fold.get("fold_index"),
            "prior_residual_count": len(prior_residuals),
            "evaluated_row_count": int(usable.sum()),
        }

        if len(prior_residuals) >= minimum_residuals and usable.any():
            low = float(np.quantile(prior_residuals, tail))
            high = float(np.quantile(prior_residuals, 1.0 - tail))
            lower = predicted[usable] * math.exp(low)
            upper = predicted[usable] * math.exp(high)
            entry["interval_available"] = True
            entry["log_residual_quantiles"] = [round(low, 6), round(high, 6)]
            entry["coverage"] = interval_coverage(actual[usable], lower, upper)
            entry["target_coverage"] = coverage
            entry["mean_interval_width_pct"] = round(float(np.mean(upper - lower)), 6)
        else:
            entry["interval_available"] = False
            entry["coverage"] = None
            entry["reason"] = (
                "no prior out-of-fold residuals"
                if not prior_residuals
                else f"only {len(prior_residuals)} prior residuals; "
                f"{minimum_residuals} required"
            )
        results.append(entry)

        # Only AFTER scoring do this fold's residuals become available to
        # later folds. Appending before scoring would leak the fold into its
        # own interval.
        prior_residuals.extend(
            np.log(actual[usable] / predicted[usable]).tolist()
        )
    return results


def aggregate_interval_coverage(fold_intervals: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Coverage pooled across folds that actually produced an interval."""
    available = [f for f in fold_intervals if f.get("interval_available")]
    if not available:
        return {"folds_with_intervals": 0, "aggregate_coverage": None}
    weights = [f["evaluated_row_count"] for f in available]
    covered = [f["coverage"] * f["evaluated_row_count"] for f in available]
    total = sum(weights)
    return {
        "folds_with_intervals": len(available),
        "aggregate_coverage": round(sum(covered) / total, 6) if total else None,
        "target_coverage": available[0].get("target_coverage"),
    }


# --- mandate-ceiling calibration --------------------------------------------


def evaluate_ceiling_calibration(
    actual: Sequence[float],
    predicted_probability: Sequence[float],
    *,
    ceiling_pct: float,
    n_bins: int = 10,
    maximum_brier: float | None = None,
) -> dict[str, Any]:
    """Brier, log loss, and a calibration curve for "volatility exceeds the
    mandate ceiling" (plan 9.4, strategy doc 8.3).

    `calibration_status` is the field that matters: a probability may only
    be presented as calibrated once it has been MEASURED against a
    preregistered bar. Absent that bar, or failing it, the probability is
    marked experimental -- doc 16 forbids displaying a raw model output as
    confidence until calibration has been measured and its meaning stated.
    """
    if not math.isfinite(ceiling_pct) or ceiling_pct <= 0:
        raise VolatilityEvaluationError("ceiling_pct must be a positive finite number")

    actual_array = np.asarray(actual, dtype=float)
    probability_array = np.asarray(predicted_probability, dtype=float)
    usable = np.isfinite(actual_array) & np.isfinite(probability_array)
    outcomes = (actual_array[usable] > ceiling_pct).astype(float)
    probabilities = probability_array[usable]

    event_count = int(len(outcomes))
    positives = int(outcomes.sum())
    result: dict[str, Any] = {
        "ceiling_pct": ceiling_pct,
        "event_count": event_count,
        "breach_count": positives,
        "breach_rate": round(float(outcomes.mean()), 6) if event_count else None,
    }
    if event_count < MIN_EVENTS_FOR_CALIBRATION or positives == 0 or positives == event_count:
        # A calibration curve fitted to a single class is meaningless: the
        # model can score a perfect Brier by always predicting the one
        # outcome that ever occurred.
        result.update(
            brier_score=None,
            log_loss=None,
            calibration=[],
            calibration_status=CalibrationStatus.NOT_MEASURED,
            insufficiency_reason=(
                f"only {event_count} events with {positives} breaches; "
                f"{MIN_EVENTS_FOR_CALIBRATION} events and both classes required"
            ),
        )
        return result

    brier = brier_score(outcomes, probabilities)
    result.update(
        brier_score=brier,
        log_loss=log_loss(outcomes, probabilities),
        calibration=calibration_curve(outcomes, probabilities, n_bins=n_bins),
    )
    if maximum_brier is None:
        result["calibration_status"] = CalibrationStatus.EXPERIMENTAL
        result["calibration_note"] = (
            "measured but no preregistered maximum_brier was declared, so this "
            "probability is experimental and must not be labeled confidence"
        )
    elif brier is not None and brier <= maximum_brier:
        result["calibration_status"] = CalibrationStatus.CALIBRATED
        result["preregistered_maximum_brier"] = maximum_brier
    else:
        result["calibration_status"] = CalibrationStatus.EXPERIMENTAL
        result["preregistered_maximum_brier"] = maximum_brier
    return result


# --- warning behavior -------------------------------------------------------


def evaluate_warning_behavior(
    frame: pd.DataFrame,
    *,
    session_column: str = "as_of_session",
    actual_column: str = "actual",
    model_column: str = "model_predicted",
    trailing_column: str = "trailing_predicted",
    ceiling_pct: float,
    subject_column: str = "ticker",
) -> dict[str, Any]:
    """Warning lead time and false-warning rate versus trailing volatility
    (plan 9.4).

    The economically interesting question is not "is QLIKE lower" but "does
    this warn EARLIER than simply looking at trailing volatility, without
    crying wolf more often". A model that warns at the same time as trailing
    vol adds nothing operationally, however much better its loss looks.

    Lead time is measured in sessions from each model's first warning to the
    start of the breach episode it precedes; positive means it warned before
    the breach began.
    """
    for column in (session_column, actual_column, model_column, trailing_column):
        if column not in frame.columns:
            raise VolatilityEvaluationError(f"frame is missing column {column!r}")

    # A per-security report may contain several rows for one session.  Those
    # rows are independent timelines, not adjacent moments in one portfolio
    # timeline.  Group before finding contiguous breach episodes; otherwise a
    # calm BBB row between two consecutive AAA breaches manufactures two
    # episodes and erases AAA's genuine warning lead time.
    if subject_column in frame.columns:
        groups = list(frame.groupby(subject_column, sort=True, dropna=False))
    else:
        groups = [("__all_subjects__", frame)]

    def _subject_summary(subject_frame: pd.DataFrame) -> dict[str, Any]:
        ordered = subject_frame.sort_values(session_column).reset_index(drop=True)
        breach = pd.to_numeric(ordered[actual_column], errors="coerce") > ceiling_pct
        episode_starts: list[int] = []
        previous = False
        for index, value in enumerate(breach):
            if bool(value) and not previous:
                episode_starts.append(index)
            previous = bool(value)

        result: dict[str, Any] = {
            "session_count": int(len(ordered)),
            "breach_episode_count": len(episode_starts),
            "non_breach_session_count": int((~breach).sum()),
        }
        for label, column in (("model", model_column), ("trailing", trailing_column)):
            warned = pd.to_numeric(ordered[column], errors="coerce") > ceiling_pct
            leads: list[int] = []
            for start in episode_starts:
                lead = 0
                position = start - 1
                while position >= 0 and bool(warned.iloc[position]):
                    lead += 1
                    position -= 1
                leads.append(lead)
            false_warnings = int((warned & ~breach).sum())
            result[label] = {
                "warning_count": int(warned.sum()),
                "leads": leads,
                "false_warning_count": false_warnings,
            }
        return result

    subject_summaries = {
        str(subject): _subject_summary(subject_frame) for subject, subject_frame in groups
    }
    summary: dict[str, Any] = {
        "ceiling_pct": ceiling_pct,
        "session_count": int(len(frame)),
        "subject_count": len(subject_summaries),
        "breach_episode_count": sum(
            value["breach_episode_count"] for value in subject_summaries.values()
        ),
        "per_subject": {
            subject: {
                "breach_episode_count": value["breach_episode_count"],
                "model": {
                    "warning_count": value["model"]["warning_count"],
                    "mean_lead_sessions": (
                        round(float(np.mean(value["model"]["leads"])), 6)
                        if value["model"]["leads"]
                        else None
                    ),
                },
                "trailing": {
                    "warning_count": value["trailing"]["warning_count"],
                    "mean_lead_sessions": (
                        round(float(np.mean(value["trailing"]["leads"])), 6)
                        if value["trailing"]["leads"]
                        else None
                    ),
                },
            }
            for subject, value in subject_summaries.items()
        },
    }
    for label in ("model", "trailing"):
        leads = [
            lead
            for value in subject_summaries.values()
            for lead in value[label]["leads"]
        ]
        false_warnings = sum(
            value[label]["false_warning_count"] for value in subject_summaries.values()
        )
        warning_count = sum(
            value[label]["warning_count"] for value in subject_summaries.values()
        )
        non_breach_sessions = sum(
            value["non_breach_session_count"] for value in subject_summaries.values()
        )
        summary[label] = {
            "warning_count": warning_count,
            "mean_lead_sessions": round(float(np.mean(leads)), 6) if leads else None,
            "episodes_warned_in_advance": int(sum(1 for lead in leads if lead > 0)),
            "false_warning_count": false_warnings,
            "false_warning_rate": (
                round(false_warnings / non_breach_sessions, 6)
                if non_breach_sessions
                else None
            ),
        }
    model_lead = summary["model"]["mean_lead_sessions"]
    trailing_lead = summary["trailing"]["mean_lead_sessions"]
    summary["model_warns_earlier_than_trailing"] = (
        model_lead is not None and trailing_lead is not None and model_lead > trailing_lead
    )
    return summary


# --- performance slices -----------------------------------------------------


def evaluate_by_slice(
    frame: pd.DataFrame,
    *,
    actual_column: str = "actual",
    predicted_column: str = "model_predicted",
    baseline_column: str = "ewma_predicted",
    slice_columns: Sequence[str] = ("year", "ticker", "volatility_regime", "earnings_proximity"),
    minimum_rows: int = 20,
) -> dict[str, Any]:
    """QLIKE/MAE by year, ticker, volatility regime, and earnings proximity
    (plan 9.4).

    Slices with too few rows are reported as insufficient rather than
    dropped. A silently missing slice reads as "nothing to see"; an
    explicitly insufficient one reads as "we could not tell" -- and this
    project has repeatedly been burned by small-sample results that looked
    real.
    """
    results: dict[str, Any] = {}
    for column in slice_columns:
        if column not in frame.columns:
            results[column] = {"available": False, "reason": "column not present"}
            continue
        buckets: list[dict[str, Any]] = []
        for value, group in frame.groupby(column, sort=True, dropna=False):
            actual = pd.to_numeric(group[actual_column], errors="coerce").to_numpy(dtype=float)
            predicted = pd.to_numeric(group[predicted_column], errors="coerce").to_numpy(dtype=float)
            baseline = pd.to_numeric(group[baseline_column], errors="coerce").to_numpy(dtype=float)
            usable = (
                np.isfinite(actual) & np.isfinite(predicted) & np.isfinite(baseline)
                & (actual > 0) & (predicted > 0) & (baseline > 0)
            )
            entry: dict[str, Any] = {
                "value": str(value),
                "row_count": int(len(group)),
                "usable_row_count": int(usable.sum()),
            }
            if usable.sum() < minimum_rows:
                entry.update(
                    sufficient=False,
                    reason=f"only {int(usable.sum())} usable rows; {minimum_rows} required",
                )
            else:
                model_qlike = qlike_loss(actual[usable], predicted[usable])
                baseline_qlike = qlike_loss(actual[usable], baseline[usable])
                entry.update(
                    sufficient=True,
                    model_qlike=model_qlike,
                    baseline_qlike=baseline_qlike,
                    model_mae=mean_absolute_error(actual[usable], predicted[usable]),
                    baseline_mae=mean_absolute_error(actual[usable], baseline[usable]),
                    model_beats_baseline=(
                        model_qlike is not None
                        and baseline_qlike is not None
                        and model_qlike < baseline_qlike
                    ),
                )
            buckets.append(entry)
        sufficient = [b for b in buckets if b.get("sufficient")]
        won = [b for b in sufficient if b.get("model_beats_baseline")]
        results[column] = {
            "available": True,
            "buckets": buckets,
            "sufficient_bucket_count": len(sufficient),
            "buckets_won": len(won),
            # Doc 8.3: "A small aggregate win produced by one crisis window
            # is insufficient." This is the number that exposes it.
            "win_fraction": (
                round(len(won) / len(sufficient), 6) if sufficient else None
            ),
        }
    return results


# --- typed shadow forecast (plan 9.5) ---------------------------------------


@dataclasses.dataclass(frozen=True)
class ShadowVolatilityForecast:
    """Everything plan 9.5 requires on a shadow forecast, in one record."""

    task: str
    subject_key: str
    model_key: str
    artifact_hash: str
    as_of_session: str
    target_available_at: str
    horizon_sessions: int
    daily_volatility_pct: float | None
    prediction_interval_daily_pct: tuple[float, float] | None
    probability_above_ceiling: float | None
    calibration_status: str
    trailing_baseline_daily_pct: float | None
    ewma_baseline_daily_pct: float | None
    feature_freshness: Mapping[str, Any]
    evidence_status: str
    available: bool
    refusal_reasons: tuple[str, ...] = ()

    WHAT_THIS_DOES_NOT_MEAN = (
        "This is an experimental estimate of how much this position or "
        "portfolio may fluctuate. It is not a prediction of direction, not a "
        "recommendation to buy or sell, and not used by the execution gate. "
        "A higher or lower number does not imply any action."
    )

    def __post_init__(self) -> None:
        if self.task != "volatility_forecast":
            raise VolatilityEvaluationError(
                "task must be 'volatility_forecast' for a ShadowVolatilityForecast"
            )
        for name in ("subject_key", "model_key"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise VolatilityEvaluationError(f"{name} must be a non-empty string")
        if not isinstance(self.artifact_hash, str) or _SHA256.fullmatch(self.artifact_hash) is None:
            raise VolatilityEvaluationError("artifact_hash must be a lowercase SHA-256 hash")
        try:
            session = pd.to_datetime(self.as_of_session, format="%Y-%m-%d", errors="coerce")
        except (TypeError, ValueError):
            session = pd.NaT
        if pd.isna(session) or session.strftime("%Y-%m-%d") != self.as_of_session:
            raise VolatilityEvaluationError("as_of_session must use canonical YYYY-MM-DD format")
        if not isinstance(self.target_available_at, str):
            raise VolatilityEvaluationError("target_available_at must be timezone-aware ISO-8601")
        try:
            available_at = datetime.fromisoformat(self.target_available_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise VolatilityEvaluationError(
                "target_available_at must be timezone-aware ISO-8601"
            ) from exc
        if available_at.tzinfo is None or available_at.utcoffset() is None:
            raise VolatilityEvaluationError("target_available_at must be timezone-aware ISO-8601")
        if (
            isinstance(self.horizon_sessions, bool)
            or not isinstance(self.horizon_sessions, int)
            or self.horizon_sessions < 1
        ):
            raise VolatilityEvaluationError("horizon_sessions must be a positive integer")
        if self.evidence_status not in _NON_AUTHORITATIVE_EVIDENCE:
            raise VolatilityEvaluationError(
                "evidence_status is not a recognized non-authoritative state"
            )
        if not isinstance(self.available, bool):
            raise VolatilityEvaluationError("available must be a boolean")
        if not isinstance(self.refusal_reasons, tuple) or any(
            not isinstance(reason, str) or not reason.strip() for reason in self.refusal_reasons
        ):
            raise VolatilityEvaluationError(
                "refusal_reasons must be a tuple of non-empty strings"
            )
        if not isinstance(self.feature_freshness, Mapping):
            raise VolatilityEvaluationError("feature_freshness must be a mapping")
        if self.calibration_status not in CalibrationStatus.ALL:
            raise VolatilityEvaluationError(
                f"calibration_status must be one of {CalibrationStatus.ALL}"
            )
        if self.available and self.refusal_reasons:
            raise VolatilityEvaluationError(
                "an available forecast cannot carry refusal reasons"
            )
        if not self.available and not self.refusal_reasons:
            raise VolatilityEvaluationError(
                "an unavailable forecast must carry at least one refusal reason"
            )
        def _optional_daily_value(value: float | None, name: str) -> None:
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value < 0
            ):
                raise VolatilityEvaluationError(f"{name} must be a non-negative finite daily percent")

        _optional_daily_value(self.trailing_baseline_daily_pct, "trailing_baseline_daily_pct")
        _optional_daily_value(self.ewma_baseline_daily_pct, "ewma_baseline_daily_pct")
        if self.available:
            if (
                self.daily_volatility_pct is None
                or isinstance(self.daily_volatility_pct, bool)
                or not isinstance(self.daily_volatility_pct, (int, float))
                or not math.isfinite(float(self.daily_volatility_pct))
                or self.daily_volatility_pct < 0
            ):
                raise VolatilityEvaluationError(
                    "an available forecast requires a non-negative finite daily volatility"
                )
            if (
                not isinstance(self.prediction_interval_daily_pct, tuple)
                or len(self.prediction_interval_daily_pct) != 2
            ):
                raise VolatilityEvaluationError("an available forecast requires a two-sided interval")
            lower, upper = self.prediction_interval_daily_pct
            if not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                and value >= 0
                for value in (lower, upper)
            ) or lower > self.daily_volatility_pct or upper < self.daily_volatility_pct:
                raise VolatilityEvaluationError(
                    "prediction interval must be finite, ordered, and contain the point forecast"
                )
            if (
                self.probability_above_ceiling is None
                or isinstance(self.probability_above_ceiling, bool)
                or not isinstance(self.probability_above_ceiling, (int, float))
                or not math.isfinite(float(self.probability_above_ceiling))
                or not 0 <= self.probability_above_ceiling <= 1
            ):
                raise VolatilityEvaluationError("ceiling probability must be within [0, 1]")
        elif any(
            value is not None
            for value in (
                self.daily_volatility_pct,
                self.prediction_interval_daily_pct,
                self.probability_above_ceiling,
            )
        ):
            raise VolatilityEvaluationError(
                "an unavailable forecast cannot carry numeric predictions"
            )

    @property
    def production_authoritative(self) -> bool:
        return False

    @property
    def annualized_volatility_pct(self) -> float | None:
        if self.daily_volatility_pct is None:
            return None
        return round(
            float(self.daily_volatility_pct * math.sqrt(TRADING_SESSIONS_PER_YEAR)), 6
        )

    @property
    def probability_label(self) -> str:
        """Never "confidence" unless calibration actually cleared its gate.

        Strategy doc 16: "Never display a raw model probability as
        'confidence' unless calibration has been measured and the exact
        meaning is stated."
        """
        if self.calibration_status == CalibrationStatus.CALIBRATED:
            return "calibrated_probability"
        return "experimental_probability"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "subject_key": self.subject_key,
            "model_key": self.model_key,
            "artifact_hash": self.artifact_hash,
            "as_of_session": self.as_of_session,
            "target_available_at": self.target_available_at,
            "horizon_sessions": self.horizon_sessions,
            "daily_volatility_pct": self.daily_volatility_pct,
            "annualized_volatility_pct": self.annualized_volatility_pct,
            "prediction_interval_daily_pct": (
                list(self.prediction_interval_daily_pct)
                if self.prediction_interval_daily_pct is not None
                else None
            ),
            self.probability_label: self.probability_above_ceiling,
            "calibration_status": self.calibration_status,
            "trailing_baseline_daily_pct": self.trailing_baseline_daily_pct,
            "ewma_baseline_daily_pct": self.ewma_baseline_daily_pct,
            "feature_freshness": dict(self.feature_freshness),
            "evidence_status": self.evidence_status,
            "available": self.available,
            "refusal_reasons": list(self.refusal_reasons),
            "production_authoritative": self.production_authoritative,
            "what_this_does_not_mean": self.WHAT_THIS_DOES_NOT_MEAN,
        }
