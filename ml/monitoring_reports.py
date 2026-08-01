"""ML-LR-7 epoch-scoped, dependence-aware shadow monitoring.

Every function in this module is pure reporting.  It never writes to storage,
loads a registry, fits a model, or changes model status.  The independent unit
for the currently supported volatility task is a scheduled market date: ticker
rows sharing that date are collapsed before a sample count or conclusion is
formed.
"""
from __future__ import annotations

import dataclasses
import math
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import numpy as np

from ml.hashing import hash_payload
from ml.monitoring import feature_health_report, lineage_consistency


class MonitoringReportError(ValueError):
    """Epoch evidence or a preregistered monitoring policy is inconsistent."""


@dataclasses.dataclass(frozen=True)
class ShadowMonitoringGate:
    """Exact review thresholds frozen before shadow outcomes are observed.

    This deliberately has no project-wide default sample count.  LR-7 requires
    the confirmation spec to justify its sample from task frequency, overlap,
    effect size, and power; a missing gate is therefore reported as a blocker,
    never silently replaced with a convenient small number.
    """

    minimum_unique_dates: int
    rolling_window_unique_dates: int
    minimum_slice_unique_dates: int
    minimum_regime_count: int
    minimum_prediction_coverage: float
    maximum_refusal_fraction: float
    target_interval_coverage: float
    interval_coverage_tolerance: float
    mandate_ceiling_daily_pct: float
    maximum_brier: float
    maximum_feature_psi: float
    maximum_output_mean_shift_fraction: float
    minimum_model_better_date_fraction: float
    sample_size_justification: str

    def __post_init__(self) -> None:
        for name in (
            "minimum_unique_dates",
            "rolling_window_unique_dates",
            "minimum_slice_unique_dates",
            "minimum_regime_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise MonitoringReportError(f"{name} must be a positive integer")
        if self.rolling_window_unique_dates > self.minimum_unique_dates:
            raise MonitoringReportError(
                "rolling_window_unique_dates cannot exceed minimum_unique_dates"
            )
        for name in (
            "minimum_prediction_coverage",
            "target_interval_coverage",
            "interval_coverage_tolerance",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 < float(value) <= 1
            ):
                raise MonitoringReportError(f"{name} must be within (0, 1]")
        if (
            isinstance(self.maximum_refusal_fraction, bool)
            or not isinstance(self.maximum_refusal_fraction, (int, float))
            or not 0 <= float(self.maximum_refusal_fraction) < 1
        ):
            raise MonitoringReportError(
                "maximum_refusal_fraction must be within [0, 1)"
            )
        if not _positive_finite(self.mandate_ceiling_daily_pct):
            raise MonitoringReportError(
                "mandate_ceiling_daily_pct must be positive and finite"
            )
        if (
            isinstance(self.maximum_brier, bool)
            or not isinstance(self.maximum_brier, (int, float))
            or not 0 < float(self.maximum_brier) <= 1
        ):
            raise MonitoringReportError("maximum_brier must be within (0, 1]")
        if not _positive_finite(self.maximum_feature_psi):
            raise MonitoringReportError("maximum_feature_psi must be positive and finite")
        if (
            isinstance(self.maximum_output_mean_shift_fraction, bool)
            or not isinstance(self.maximum_output_mean_shift_fraction, (int, float))
            or not 0 <= float(self.maximum_output_mean_shift_fraction) <= 1
        ):
            raise MonitoringReportError(
                "maximum_output_mean_shift_fraction must be within [0, 1]"
            )
        if (
            isinstance(self.minimum_model_better_date_fraction, bool)
            or not isinstance(self.minimum_model_better_date_fraction, (int, float))
            or not 0 <= float(self.minimum_model_better_date_fraction) <= 1
        ):
            raise MonitoringReportError(
                "minimum_model_better_date_fraction must be within [0, 1]"
            )
        if not isinstance(self.sample_size_justification, str) or not self.sample_size_justification.strip():
            raise MonitoringReportError(
                "sample_size_justification must explain frequency, overlap, effect size, and power"
            )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_confirmation_spec(
        cls, payload: Mapping[str, Any]
    ) -> "ShadowMonitoringGate | None":
        task_parameters = payload.get("task_parameters")
        if not isinstance(task_parameters, Mapping):
            return None
        raw = task_parameters.get("shadow_monitoring_gate")
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            raise MonitoringReportError(
                "task_parameters.shadow_monitoring_gate must be an object"
            )
        try:
            return cls(**dict(raw))
        except TypeError as exc:
            raise MonitoringReportError(
                f"invalid shadow_monitoring_gate fields: {exc}"
            ) from exc


def _positive_finite(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) > 0
    )


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _parse_instant(value: Any, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise MonitoringReportError(f"{name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MonitoringReportError(f"{name} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _prediction_payload(row: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = row.get("prediction")
    return payload if isinstance(payload, Mapping) else row


def _values(row: Mapping[str, Any]) -> Mapping[str, Any]:
    values = _prediction_payload(row).get("values")
    return values if isinstance(values, Mapping) else {}


def _uncertainty(row: Mapping[str, Any]) -> Mapping[str, Any]:
    uncertainty = _prediction_payload(row).get("uncertainty")
    return uncertainty if isinstance(uncertainty, Mapping) else {}


def _monitoring_features(row: Mapping[str, Any]) -> Mapping[str, Any]:
    features = _prediction_payload(row).get("monitoring_features")
    return features if isinstance(features, Mapping) else {}


def _context(row: Mapping[str, Any]) -> Mapping[str, Any]:
    context = _prediction_payload(row).get("monitoring_context")
    return context if isinstance(context, Mapping) else {}


def _group_mean(rows: Sequence[tuple[str, float]]) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for session, value in rows:
        grouped.setdefault(session, []).append(value)
    return {
        session: float(np.mean(values)) for session, values in sorted(grouped.items())
    }


def _group_median(rows: Sequence[tuple[str, float]]) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for session, value in rows:
        grouped.setdefault(session, []).append(value)
    return {
        session: float(np.median(values))
        for session, values in sorted(grouped.items())
    }


def _sufficiency(
    sufficient: bool,
    *,
    independent_count: int,
    required_count: int | None,
    reasons: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "sufficient": bool(sufficient),
        "independent_observation_count": independent_count,
        "required_independent_observation_count": required_count,
        "insufficiency_reasons": [] if sufficient else list(dict.fromkeys(reasons)),
    }


def _coverage(
    predictions: Sequence[Mapping[str, Any]],
    runs: Sequence[Mapping[str, Any]],
    expected_subjects: Sequence[str],
    gate: ShadowMonitoringGate | None,
) -> dict[str, Any]:
    expected = len(runs) * len(tuple(expected_subjects))
    available = sum(bool(row.get("available")) for row in predictions)
    refused = len(predictions) - available
    reasons = Counter(
        str(reason)
        for row in predictions
        if not row.get("available")
        for reason in (row.get("refusal_reasons") or ())
    )
    scheduled_dates = {str(row.get("scheduled_for", ""))[:10] for row in runs}
    prediction_coverage = len(predictions) / expected if expected else None
    refusal_fraction = refused / len(predictions) if predictions else None
    sufficient = bool(
        gate
        and len(scheduled_dates) >= gate.minimum_unique_dates
        and prediction_coverage is not None
        and prediction_coverage >= gate.minimum_prediction_coverage
        and refusal_fraction is not None
        and refusal_fraction <= gate.maximum_refusal_fraction
        and (refused == 0 or bool(reasons))
    )
    insufficiency: list[str] = []
    if gate is None:
        insufficiency.append("no_preregistered_shadow_monitoring_gate")
    else:
        if len(scheduled_dates) < gate.minimum_unique_dates:
            insufficiency.append("too_few_unique_scheduled_dates")
        if prediction_coverage is None or prediction_coverage < gate.minimum_prediction_coverage:
            insufficiency.append("prediction_coverage_below_gate")
        if refusal_fraction is None or refusal_fraction > gate.maximum_refusal_fraction:
            insufficiency.append("refusal_fraction_above_gate")
        if refused and not reasons:
            insufficiency.append("unexplained_refusals")
    return {
        "scheduled_attempt_count": len(runs),
        "unique_scheduled_date_count": len(scheduled_dates),
        "expected_subject_attempt_count": expected,
        "recorded_subject_attempt_count": len(predictions),
        "available_count": available,
        "refused_count": refused,
        "prediction_coverage": round(prediction_coverage, 6) if prediction_coverage is not None else None,
        "refusal_fraction": round(refusal_fraction, 6) if refusal_fraction is not None else None,
        "refusal_reason_counts": dict(sorted(reasons.items())),
        "run_status_counts": dict(sorted(Counter(str(row.get("status")) for row in runs).items())),
        "sample_sufficiency": _sufficiency(
            sufficient,
            independent_count=len(scheduled_dates),
            required_count=gate.minimum_unique_dates if gate else None,
            reasons=insufficiency,
        ),
    }


def _psi_from_reference(
    summary: Mapping[str, Any], current_values: Sequence[float]
) -> dict[str, Any]:
    edges = np.asarray(summary.get("bin_edges", ()), dtype=float)
    reference_counts = np.asarray(summary.get("bin_counts", ()), dtype=float)
    current = np.asarray(current_values, dtype=float)
    current = current[np.isfinite(current)]
    if (
        current.size == 0
        or reference_counts.size != edges.size + 1
        or reference_counts.sum() <= 0
    ):
        return {
            "psi": None,
            "interpretation": "unavailable",
            "current_independent_date_count": int(current.size),
            "out_of_training_range_count": 0,
        }
    current_counts, _ = np.histogram(
        current, bins=np.concatenate(([-np.inf], edges, [np.inf]))
    )
    epsilon = 1e-6
    reference_share = np.clip(reference_counts / reference_counts.sum(), epsilon, None)
    current_share = np.clip(current_counts / current_counts.sum(), epsilon, None)
    psi = float(np.sum((current_share - reference_share) * np.log(current_share / reference_share)))
    minimum = _finite(summary.get("minimum"))
    maximum = _finite(summary.get("maximum"))
    outside = int(
        sum(
            (minimum is not None and value < minimum)
            or (maximum is not None and value > maximum)
            for value in current
        )
    )
    interpretation = "stable" if psi < 0.10 else "moderate_shift" if psi < 0.25 else "significant_shift"
    return {
        "psi": round(psi, 6),
        "interpretation": interpretation,
        "interpretation_bands": "psi<0.10 stable; 0.10-0.25 moderate; >0.25 significant",
        "reference_independent_date_count": int(reference_counts.sum()),
        "current_independent_date_count": int(current.size),
        "out_of_training_range_count": outside,
        "current_minimum": round(float(current.min()), 6),
        "current_maximum": round(float(current.max()), 6),
        "mean_shift": (
            round(float(current.mean()) - float(summary["mean"]), 6)
            if _finite(summary.get("mean")) is not None
            else None
        ),
    }


def _feature_drift(
    predictions: Sequence[Mapping[str, Any]],
    feature_reference: Mapping[str, Any] | None,
    gate: ShadowMonitoringGate | None,
) -> dict[str, Any]:
    if not feature_reference:
        return {
            "features": {},
            "sample_sufficiency": _sufficiency(
                False,
                independent_count=0,
                required_count=gate.minimum_unique_dates if gate else None,
                reasons=("model_artifact_has_no_frozen_feature_reference",),
            ),
        }
    reports: dict[str, Any] = {}
    counts: list[int] = []
    for name, summary in sorted(feature_reference.items()):
        rows: list[tuple[str, float]] = []
        for prediction in predictions:
            value = _finite(_monitoring_features(prediction).get(name))
            if value is not None:
                rows.append((str(prediction.get("as_of_session")), value))
        date_values = list(_group_median(rows).values())
        feature_report = _psi_from_reference(summary, date_values)
        reference_count = int(summary.get("independent_date_count", 0))
        independent_count = min(len(date_values), reference_count)
        counts.append(independent_count)
        feature_report["maximum_psi"] = gate.maximum_feature_psi if gate else None
        feature_report["drift_acceptable"] = bool(
            gate
            and independent_count >= gate.minimum_unique_dates
            and feature_report.get("psi") is not None
            and feature_report["psi"] <= gate.maximum_feature_psi
        )
        reports[name] = feature_report
    independent = min(counts) if counts else 0
    sufficient = bool(gate and counts and independent >= gate.minimum_unique_dates)
    return {
        "features": reports,
        "aggregation": "median_by_as_of_session_before_drift",
        "all_feature_drift_acceptable": bool(
            reports and all(report["drift_acceptable"] for report in reports.values())
        ),
        "sample_sufficiency": _sufficiency(
            sufficient,
            independent_count=independent,
            required_count=gate.minimum_unique_dates if gate else None,
            reasons=(
                "no_preregistered_shadow_monitoring_gate"
                if gate is None
                else "too_few_unique_dates_for_feature_drift",
            ),
        ),
    }


def _output_drift(
    predictions: Sequence[Mapping[str, Any]], gate: ShadowMonitoringGate | None
) -> dict[str, Any]:
    rows = [
        (str(row.get("as_of_session")), value)
        for row in predictions
        if row.get("available")
        for value in [_finite(_values(row).get("daily_volatility_pct"))]
        if value is not None
    ]
    by_date = _group_mean(rows)
    values = list(by_date.values())
    midpoint = len(values) // 2
    if midpoint == 0 or midpoint == len(values):
        report = {
            "mean_shift": None,
            "absolute_mean_shift_fraction": None,
            "standard_deviation_ratio": None,
        }
    else:
        reference = np.asarray(values[:midpoint], dtype=float)
        current = np.asarray(values[midpoint:], dtype=float)
        reference_std = float(reference.std(ddof=1)) if len(reference) > 1 else math.nan
        current_std = float(current.std(ddof=1)) if len(current) > 1 else math.nan
        report = {
            "mean_shift": round(float(current.mean() - reference.mean()), 6),
            "absolute_mean_shift_fraction": (
                round(abs(float(current.mean() - reference.mean())) / abs(float(reference.mean())), 6)
                if float(reference.mean()) != 0
                else None
            ),
            "standard_deviation_ratio": (
                round(current_std / reference_std, 6)
                if math.isfinite(reference_std) and reference_std > 0 and math.isfinite(current_std)
                else None
            ),
        }
    half_required = math.ceil(gate.minimum_unique_dates / 2) if gate else None
    sufficient = bool(gate and midpoint >= half_required and len(values) - midpoint >= half_required)
    drift_acceptable = bool(
        gate
        and sufficient
        and report["absolute_mean_shift_fraction"] is not None
        and report["absolute_mean_shift_fraction"]
        <= gate.maximum_output_mean_shift_fraction
    )
    return {
        **report,
        "reference_unique_date_count": midpoint,
        "current_unique_date_count": len(values) - midpoint,
        "maximum_mean_shift_fraction": (
            gate.maximum_output_mean_shift_fraction if gate else None
        ),
        "drift_acceptable": drift_acceptable,
        "sample_sufficiency": _sufficiency(
            sufficient,
            independent_count=min(midpoint, len(values) - midpoint),
            required_count=half_required,
            reasons=(
                "no_preregistered_shadow_monitoring_gate"
                if gate is None
                else "too_few_unique_dates_in_drift_halves",
            ),
        ),
    }


def _matured_rows(
    predictions: Sequence[Mapping[str, Any]], outcomes: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    by_id = {str(row.get("prediction_id")): row for row in outcomes}
    result: list[dict[str, Any]] = []
    for prediction in predictions:
        outcome = by_id.get(str(prediction.get("prediction_id")))
        if outcome is None:
            continue
        actual = _finite(
            (outcome.get("outcome") or {}).get("realized_daily_volatility_pct")
            if isinstance(outcome.get("outcome"), Mapping)
            else None
        )
        model = _finite(_values(prediction).get("daily_volatility_pct"))
        if actual is None or model is None:
            continue
        result.append(
            {
                "session": str(prediction.get("as_of_session")),
                "ticker": str(prediction.get("subject_key")),
                "actual": actual,
                "model": model,
                "trailing": _finite(_values(prediction).get("trailing_baseline_daily_pct")),
                "ewma": _finite(_values(prediction).get("ewma_baseline_daily_pct")),
                "uncertainty": _uncertainty(prediction),
                "event_category": str(_context(prediction).get("event_category", "unavailable")),
            }
        )
    return result


def _qlike(actual: float, predicted: float) -> float:
    if actual <= 0 or predicted <= 0:
        return math.nan
    ratio = (actual / predicted) ** 2
    return ratio - math.log(ratio) - 1.0


def _date_level_losses(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, float]:
    losses: list[tuple[str, float]] = []
    for row in rows:
        predicted = _finite(row.get(key))
        if predicted is None:
            continue
        loss = _qlike(float(row["actual"]), predicted)
        if math.isfinite(loss):
            losses.append((str(row["session"]), loss))
    return _group_mean(losses)


def _realized_and_baselines(
    rows: Sequence[Mapping[str, Any]], gate: ShadowMonitoringGate | None
) -> tuple[dict[str, Any], dict[str, Any]]:
    model_losses = _date_level_losses(rows, "model")
    errors = _group_mean(
        [(str(row["session"]), abs(float(row["actual"]) - float(row["model"]))) for row in rows]
    )
    signed = _group_mean(
        [(str(row["session"]), float(row["actual"]) - float(row["model"])) for row in rows]
    )
    window = gate.rolling_window_unique_dates if gate else None
    rolling: list[dict[str, Any]] = []
    if window is not None:
        sessions = sorted(errors)
        for index in range(window - 1, len(sessions)):
            selected = sessions[index - window + 1 : index + 1]
            rolling.append(
                {
                    "as_of_session": sessions[index],
                    "mae": round(float(np.mean([errors[item] for item in selected])), 6),
                }
            )
    independent = len(model_losses)
    sufficient = bool(gate and independent >= gate.minimum_unique_dates)
    realized = {
        "matured_row_count": len(rows),
        "independent_unique_date_count": independent,
        "overall_date_level_qlike": round(float(np.mean(list(model_losses.values()))), 6) if model_losses else None,
        "overall_date_level_mae": round(float(np.mean(list(errors.values()))), 6) if errors else None,
        "overall_date_level_bias": round(float(np.mean(list(signed.values()))), 6) if signed else None,
        "rolling_unique_date_mae": rolling,
        "sample_sufficiency": _sufficiency(
            sufficient,
            independent_count=independent,
            required_count=gate.minimum_unique_dates if gate else None,
            reasons=(
                "no_preregistered_shadow_monitoring_gate"
                if gate is None
                else "too_few_unique_matured_dates",
            ),
        ),
    }

    comparisons: dict[str, Any] = {}
    all_complete = True
    for baseline in ("trailing", "ewma"):
        comparable = [row for row in rows if _finite(row.get(baseline)) is not None]
        missing = len(rows) - len(comparable)
        all_complete = all_complete and missing == 0
        baseline_losses = _date_level_losses(comparable, baseline)
        comparable_model = _date_level_losses(comparable, "model")
        common = sorted(set(baseline_losses) & set(comparable_model))
        wins = sum(comparable_model[item] < baseline_losses[item] for item in common)
        comparisons[baseline] = {
            "identical_matured_row_count": len(comparable),
            "missing_baseline_row_count": missing,
            "independent_unique_date_count": len(common),
            "model_mean_qlike": round(float(np.mean([comparable_model[item] for item in common])), 6) if common else None,
            "baseline_mean_qlike": round(float(np.mean([baseline_losses[item] for item in common])), 6) if common else None,
            "model_better_date_count": wins,
            "model_better_date_fraction": round(wins / len(common), 6) if common else None,
            "minimum_model_better_date_fraction": (
                gate.minimum_model_better_date_fraction if gate else None
            ),
            "performance_gate_passed": bool(
                gate
                and missing == 0
                and len(common) >= gate.minimum_unique_dates
                and common
                and float(np.mean([comparable_model[item] for item in common]))
                < float(np.mean([baseline_losses[item] for item in common]))
                and wins / len(common) >= gate.minimum_model_better_date_fraction
            ),
            "sample_sufficiency": _sufficiency(
                bool(gate and missing == 0 and len(common) >= gate.minimum_unique_dates),
                independent_count=len(common),
                required_count=gate.minimum_unique_dates if gate else None,
                reasons=tuple(
                    reason
                    for reason, present in (
                        ("no_preregistered_shadow_monitoring_gate", gate is None),
                        ("baseline_rows_missing_from_matured_sample", missing > 0),
                        ("too_few_identical_unique_dates", bool(gate and len(common) < gate.minimum_unique_dates)),
                    )
                    if present
                ),
            ),
        }
    return realized, {
        "comparisons": comparisons,
        "all_matured_rows_have_every_frozen_baseline": all_complete,
        "note": "Candidate and baseline losses are compared only on identical matured rows, then averaged by date.",
    }


def _calibration(
    rows: Sequence[Mapping[str, Any]], gate: ShadowMonitoringGate | None
) -> dict[str, Any]:
    interval_by_date: dict[str, list[bool]] = {}
    probability_rows: list[tuple[str, float, float]] = []
    for row in rows:
        uncertainty = row["uncertainty"]
        interval = uncertainty.get("prediction_interval_daily_pct")
        if isinstance(interval, (list, tuple)) and len(interval) == 2:
            lower, upper = _finite(interval[0]), _finite(interval[1])
            if lower is not None and upper is not None and lower <= upper:
                interval_by_date.setdefault(row["session"], []).append(
                    lower <= row["actual"] <= upper
                )
        probability = _finite(
            uncertainty.get("calibrated_probability_above_mandate_ceiling")
        )
        if probability is not None and 0 <= probability <= 1 and gate and gate.mandate_ceiling_daily_pct is not None:
            probability_rows.append(
                (row["session"], probability, float(row["actual"] > gate.mandate_ceiling_daily_pct))
            )
    interval_dates = {
        session: float(np.mean(values)) for session, values in interval_by_date.items()
    }
    interval_coverage = float(np.mean(list(interval_dates.values()))) if interval_dates else None
    probability_by_date: dict[str, list[tuple[float, float]]] = {}
    for session, probability, actual in probability_rows:
        probability_by_date.setdefault(session, []).append((probability, actual))
    brier_values = [
        float(np.mean([(probability - actual) ** 2 for probability, actual in values]))
        for values in probability_by_date.values()
    ]
    brier = float(np.mean(brier_values)) if brier_values else None
    interval_ok = bool(
        gate
        and interval_coverage is not None
        and len(interval_dates) >= gate.minimum_unique_dates
        and abs(interval_coverage - gate.target_interval_coverage) <= gate.interval_coverage_tolerance
    )
    calibration_ok = bool(
        gate
        and brier is not None
        and len(probability_by_date) >= gate.minimum_unique_dates
        and brier <= float(gate.maximum_brier)
    )
    return {
        "interval": {
            "status": "measured" if interval_coverage is not None else "not_measured",
            "independent_unique_date_count": len(interval_dates),
            "observed_coverage": round(interval_coverage, 6) if interval_coverage is not None else None,
            "target_coverage": gate.target_interval_coverage if gate else None,
            "tolerance": gate.interval_coverage_tolerance if gate else None,
            "sample_sufficiency": _sufficiency(
                interval_ok,
                independent_count=len(interval_dates),
                required_count=gate.minimum_unique_dates if gate else None,
                reasons=(
                    "prediction_intervals_not_recorded"
                    if not interval_dates
                    else "interval_coverage_or_sample_gate_not_met",
                ),
            ),
        },
        "ceiling_probability": {
            "status": "measured" if brier is not None else "not_measured",
            "independent_unique_date_count": len(probability_by_date),
            "brier_score": round(brier, 6) if brier is not None else None,
            "maximum_brier": gate.maximum_brier if gate else None,
            "sample_sufficiency": _sufficiency(
                calibration_ok,
                independent_count=len(probability_by_date),
                required_count=gate.minimum_unique_dates if gate else None,
                reasons=(
                    "calibrated_probabilities_not_recorded"
                    if gate and not probability_by_date
                    else "calibration_gate_not_met",
                ),
            ),
        },
    }


def _slice_metrics(rows: Sequence[Mapping[str, Any]], key: str, gate: ShadowMonitoringGate | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    buckets: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(str(row[key]), []).append(row)
    for name, selected in sorted(buckets.items()):
        dates = {str(row["session"]) for row in selected}
        result[name] = {
            "row_count": len(selected),
            "independent_unique_date_count": len(dates),
            "mae": round(float(np.mean([abs(row["actual"] - row["model"]) for row in selected])), 6),
            "sample_sufficiency": _sufficiency(
                bool(gate and len(dates) >= gate.minimum_slice_unique_dates),
                independent_count=len(dates),
                required_count=gate.minimum_slice_unique_dates if gate else None,
                reasons=("thin_failure_slice",),
            ),
        }
    return result


def _failure_slices(rows: Sequence[Mapping[str, Any]], gate: ShadowMonitoringGate | None) -> dict[str, Any]:
    enriched: list[dict[str, Any]] = []
    actuals = [float(row["actual"]) for row in rows]
    median = float(np.median(actuals)) if actuals else None
    for row in rows:
        enriched.append(
            {
                **dict(row),
                "year": str(row["session"])[:4],
                "regime": (
                    "high_realized_volatility"
                    if median is not None and row["actual"] > median
                    else "low_realized_volatility"
                ),
            }
        )
    regimes = {row["regime"] for row in enriched}
    return {
        "year": _slice_metrics(enriched, "year", gate),
        "regime": _slice_metrics(enriched, "regime", gate),
        "ticker": _slice_metrics(enriched, "ticker", gate),
        "event_category": _slice_metrics(enriched, "event_category", gate),
        "regime_definition": "descriptive median split of matured realized volatility; never a model input",
        "regime_count": len(regimes),
        "regime_span_sufficient": bool(gate and len(regimes) >= gate.minimum_regime_count),
    }


def _outcome_underfill(
    predictions: Sequence[Mapping[str, Any]],
    outcomes: Sequence[Mapping[str, Any]],
    as_of: datetime,
) -> dict[str, Any]:
    outcome_ids = {str(row.get("prediction_id")) for row in outcomes}
    due: list[str] = []
    underfilled: list[str] = []
    for row in predictions:
        if not row.get("available"):
            continue
        target = _parse_instant(row.get("target_available_at"), "target_available_at")
        if target <= as_of:
            identifier = str(row.get("prediction_id"))
            due.append(identifier)
            if identifier not in outcome_ids:
                underfilled.append(identifier)
    return {
        "due_outcome_count": len(due),
        "recorded_due_outcome_count": len(due) - len(underfilled),
        "underfill_count": len(underfilled),
        "underfilled_prediction_ids": underfilled[:100],
        "complete": not underfilled,
    }


def _operations(runs: Sequence[Mapping[str, Any]], alerts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    failures = [row for row in runs if row.get("status") == "failed"]
    unresolved = [row for row in alerts if row.get("status") == "open"]
    return {
        "failed_run_count": len(failures),
        "failed_runs": failures,
        "historical_incident_count": len(alerts),
        "historical_incidents": list(alerts),
        "unresolved_incident_count": len(unresolved),
        "unresolved_incidents": unresolved,
        "untracked_failed_run_count": len(failures) if failures and not alerts else 0,
        "clean": not unresolved and (not failures or bool(alerts)),
        "note": "Historical incidents remain visible after later successful runs.",
    }


def build_epoch_monitoring_report(
    *,
    evidence_epoch: str,
    lineage_hash: str,
    predictions: Sequence[Mapping[str, Any]],
    outcomes: Sequence[Mapping[str, Any]],
    runs: Sequence[Mapping[str, Any]],
    operational_alerts: Sequence[Mapping[str, Any]],
    expected_subjects: Sequence[str],
    feature_reference: Mapping[str, Any] | None,
    gate: ShadowMonitoringGate | None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Build one immutable-content monitoring snapshot for exactly one epoch."""
    if not isinstance(evidence_epoch, str) or not evidence_epoch:
        raise MonitoringReportError("evidence_epoch is required")
    foreign_predictions = [
        row.get("prediction_id")
        for row in predictions
        if row.get("evidence_epoch") != evidence_epoch
    ]
    foreign_runs = [row.get("run_id") for row in runs if row.get("evidence_epoch") != evidence_epoch]
    if foreign_predictions or foreign_runs:
        raise MonitoringReportError(
            "predictions and runs from different evidence epochs cannot be pooled"
        )
    prediction_ids = {str(row.get("prediction_id")) for row in predictions}
    foreign_outcomes = [row.get("prediction_id") for row in outcomes if str(row.get("prediction_id")) not in prediction_ids]
    if foreign_outcomes:
        raise MonitoringReportError("an outcome does not belong to this evidence epoch")
    instant = _parse_instant(as_of, "as_of") if as_of else datetime.now(timezone.utc)

    coverage = _coverage(predictions, runs, expected_subjects, gate)
    feature_health = feature_health_report(predictions)
    feature_health.pop("sufficient_sample", None)
    freshness_dates = {
        str(row.get("as_of_session"))
        for row in predictions
        if row.get("as_of_session")
    }
    feature_health["sample_sufficiency"] = _sufficiency(
        bool(
            gate
            and len(freshness_dates) >= gate.minimum_unique_dates
            and feature_health["invalid_or_missing_freshness_count"] == 0
            and feature_health["future_dated_feature_prediction_count"] == 0
        ),
        independent_count=len(freshness_dates),
        required_count=gate.minimum_unique_dates if gate else None,
        reasons=tuple(
            reason
            for reason, present in (
                ("no_preregistered_shadow_monitoring_gate", gate is None),
                (
                    "too_few_unique_dates_for_feature_health",
                    bool(gate and len(freshness_dates) < gate.minimum_unique_dates),
                ),
                (
                    "invalid_missing_or_future_dated_feature_freshness",
                    feature_health["invalid_or_missing_freshness_count"] > 0
                    or feature_health["future_dated_feature_prediction_count"] > 0,
                ),
            )
            if present
        ),
    )
    feature_drift = _feature_drift(predictions, feature_reference, gate)
    output_drift = _output_drift(predictions, gate)
    matured = _matured_rows(predictions, outcomes)
    realized, baselines = _realized_and_baselines(matured, gate)
    calibration = _calibration(matured, gate)
    slices = _failure_slices(matured, gate)
    lineage = lineage_consistency(predictions)
    underfill = _outcome_underfill(predictions, outcomes, instant)
    operations = _operations(runs, operational_alerts)

    blockers: list[str] = []
    if gate is None:
        blockers.append("confirmation_shadow_monitoring_gate_missing")
    for name, section in (
        ("coverage", coverage),
        ("feature_health", feature_health),
        ("feature_drift", feature_drift),
        ("output_drift", output_drift),
        ("realized_error", realized),
    ):
        if not section["sample_sufficiency"]["sufficient"]:
            blockers.append(f"{name}_evidence_insufficient")
    if not feature_drift.get("all_feature_drift_acceptable"):
        blockers.append("feature_distribution_drift_unacceptable")
    if not output_drift.get("drift_acceptable"):
        blockers.append("output_drift_unacceptable")
    for baseline, report in baselines["comparisons"].items():
        if not report["sample_sufficiency"]["sufficient"]:
            blockers.append(f"{baseline}_baseline_comparison_insufficient")
        elif not report["performance_gate_passed"]:
            blockers.append(f"model_underperforms_{baseline}_in_shadow")
    if not calibration["interval"]["sample_sufficiency"]["sufficient"]:
        blockers.append("interval_coverage_insufficient_or_unacceptable")
    if not calibration["ceiling_probability"]["sample_sufficiency"]["sufficient"]:
        blockers.append("calibration_insufficient_or_unacceptable")
    if lineage["requires_new_evidence_epoch"] or lineage["clock_error_count"] or lineage["invalid_lineage_count"]:
        blockers.append("shadow_lineage_inconsistent")
    if not underfill["complete"]:
        blockers.append("matured_outcome_underfill")
    if not operations["clean"]:
        blockers.append("shadow_operational_incidents_present")
    if gate and not slices["regime_span_sufficient"]:
        blockers.append("shadow_regime_span_insufficient")

    payload = {
        "schema_version": "1.0",
        "generated_at": instant.isoformat(),
        "evidence_epoch": evidence_epoch,
        "lineage_hash": lineage_hash,
        "independent_observation_unit": "unique_as_of_session",
        "monitoring_gate": gate.to_dict() if gate else None,
        "coverage": coverage,
        "feature_health": feature_health,
        "feature_distribution_drift": feature_drift,
        "output_drift": output_drift,
        "realized_error": realized,
        "calibration_and_interval_coverage": calibration,
        "frozen_baseline_performance": baselines,
        "failure_slices": slices,
        "lineage_consistency": lineage,
        "target_outcome_underfill": underfill,
        "operational_failures": operations,
        "promotion_blockers": list(dict.fromkeys(blockers)),
        "conclusions_supported": not blockers,
        "production_authoritative": False,
        "notes": (
            "Read-only monitoring. Ticker rows sharing a date are never counted as "
            "independent evidence. No result retrains or promotes a model."
        ),
    }
    payload["report_hash"] = hash_payload(payload)
    return payload
