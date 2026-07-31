"""ML-6: shadow-prediction monitoring (strategy doc section 10.3).

Doc 10.3's closing line is the governing constraint on this whole module:
"Monitoring must not retrain or promote a model automatically." Everything
here is a pure read-and-report function. Nothing fits, nothing writes, and
nothing changes a model's status.

The `sufficient_sample` field on every report exists because doc 10.3
requires reporting "whether sample size is sufficient to draw any
conclusion" -- a drift or calibration number computed from 6 observations
is noise wearing a decimal point, and this project has repeatedly been
burned by small-sample results that looked real.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

MIN_OBSERVATIONS_FOR_CONCLUSION = 30


class MonitoringError(ValueError):
    """Prediction/outcome records cannot support a monitoring report."""


def coverage_report(predictions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Prediction coverage and refusal rate (doc 10.3).

    Doc 10.2 requires recording unavailable predictions too; this is the
    report that makes that pay off. A model that silently stopped producing
    output looks identical to a healthy one unless refusals are counted.
    """
    total = len(predictions)
    if total == 0:
        return {
            "total_attempts": 0,
            "available_count": 0,
            "refused_count": 0,
            "refusal_rate": None,
            "refusal_reason_counts": {},
            "sufficient_sample": False,
        }
    available = sum(1 for p in predictions if p.get("available"))
    refused = total - available
    reason_counts: dict[str, int] = {}
    for prediction in predictions:
        if prediction.get("available"):
            continue
        for reason in prediction.get("refusal_reasons", ()) or ():
            reason_counts[str(reason)] = reason_counts.get(str(reason), 0) + 1
    return {
        "total_attempts": total,
        "available_count": available,
        "refused_count": refused,
        "refusal_rate": round(refused / total, 6),
        "refusal_reason_counts": dict(sorted(reason_counts.items())),
        "sufficient_sample": total >= MIN_OBSERVATIONS_FOR_CONCLUSION,
    }


def _finite_array(values: Sequence[float]) -> np.ndarray:
    array = np.asarray(list(values), dtype=float)
    return array[np.isfinite(array)]


def distribution_drift(
    reference: Sequence[float], current: Sequence[float]
) -> dict[str, Any]:
    """Population Stability Index plus simple moment shifts (doc 10.3).

    PSI is reported with its conventional interpretation bands stated
    explicitly rather than left implicit, because "PSI = 0.18" means
    nothing without them. Bands: <0.10 stable, 0.10-0.25 moderate shift,
    >0.25 significant shift. These are industry convention, not a result
    validated on this project's own data -- treated as a triage signal for
    a human, never as an automatic trigger.
    """
    reference_values = _finite_array(reference)
    current_values = _finite_array(current)
    if reference_values.size == 0 or current_values.size == 0:
        return {
            "psi": None,
            "interpretation": "unavailable",
            "reference_count": int(reference_values.size),
            "current_count": int(current_values.size),
            "mean_shift": None,
            "std_ratio": None,
            "sufficient_sample": False,
        }

    quantiles = np.quantile(reference_values, np.linspace(0, 1, 11))
    edges = np.unique(quantiles)
    psi: float | None
    if edges.size < 3:
        # A near-constant reference distribution cannot produce meaningful
        # bins; report unavailable rather than a divide-by-zero artifact.
        psi = None
    else:
        reference_counts, _ = np.histogram(reference_values, bins=edges)
        current_counts, _ = np.histogram(current_values, bins=edges)
        reference_share = reference_counts / max(1, reference_counts.sum())
        current_share = current_counts / max(1, current_counts.sum())
        epsilon = 1e-6
        reference_share = np.clip(reference_share, epsilon, None)
        current_share = np.clip(current_share, epsilon, None)
        psi = float(
            np.sum((current_share - reference_share) * np.log(current_share / reference_share))
        )
        if not math.isfinite(psi):
            psi = None

    if psi is None:
        interpretation = "unavailable"
    elif psi < 0.10:
        interpretation = "stable"
    elif psi < 0.25:
        interpretation = "moderate_shift"
    else:
        interpretation = "significant_shift"

    reference_std = float(reference_values.std(ddof=1)) if reference_values.size > 1 else float("nan")
    current_std = float(current_values.std(ddof=1)) if current_values.size > 1 else float("nan")
    return {
        "psi": round(psi, 6) if psi is not None else None,
        "interpretation": interpretation,
        "interpretation_bands": "psi<0.10 stable; 0.10-0.25 moderate; >0.25 significant",
        "reference_count": int(reference_values.size),
        "current_count": int(current_values.size),
        "mean_shift": round(float(current_values.mean() - reference_values.mean()), 6),
        "std_ratio": (
            round(current_std / reference_std, 6)
            if math.isfinite(reference_std) and reference_std > 0 and math.isfinite(current_std)
            else None
        ),
        "sufficient_sample": (
            reference_values.size >= MIN_OBSERVATIONS_FOR_CONCLUSION
            and current_values.size >= MIN_OBSERVATIONS_FOR_CONCLUSION
        ),
    }


def realized_error_by_window(
    matured: Sequence[Mapping[str, Any]],
    *,
    predicted_key: str,
    actual_key: str,
    window: int = 20,
) -> dict[str, Any]:
    """Rolling realized error (doc 10.3), reported oldest-first."""
    if window < 2:
        raise MonitoringError("window must be at least 2")
    rows = []
    for record in matured:
        predicted = record.get(predicted_key)
        actual = record.get(actual_key)
        if predicted is None or actual is None:
            continue
        predicted_value, actual_value = float(predicted), float(actual)
        if not (math.isfinite(predicted_value) and math.isfinite(actual_value)):
            continue
        rows.append(
            {
                "as_of_session": record.get("as_of_session"),
                "error": actual_value - predicted_value,
                "absolute_error": abs(actual_value - predicted_value),
            }
        )
    if not rows:
        return {"observation_count": 0, "rolling_mae": [], "sufficient_sample": False}

    frame = pd.DataFrame(rows).sort_values("as_of_session")
    rolling = frame["absolute_error"].rolling(window).mean()
    return {
        "observation_count": len(frame),
        "overall_mae": round(float(frame["absolute_error"].mean()), 6),
        "overall_bias": round(float(frame["error"].mean()), 6),
        "rolling_mae": [
            {"as_of_session": session, "mae": round(float(value), 6)}
            for session, value in zip(frame["as_of_session"], rolling)
            if pd.notna(value)
        ],
        "sufficient_sample": len(frame) >= MIN_OBSERVATIONS_FOR_CONCLUSION,
    }


def lineage_consistency(
    predictions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Detect duplicate generation, model changes, and lineage drift (doc 10.2).

    A change in model_key or feature_snapshot_hash mid-stream means the
    accumulated shadow evidence describes two different systems. Doc 10.2
    requires starting a NEW EVIDENCE EPOCH when that happens -- pooling
    across the change would silently average two models' track records into
    one meaningless number, exactly the mistake this project's
    paper_evidence_epochs table already exists to prevent elsewhere.
    """
    model_keys = sorted({str(p.get("model_key")) for p in predictions if p.get("model_key")})
    identity_counts: dict[tuple, int] = {}
    for prediction in predictions:
        identity = (
            prediction.get("model_key"),
            prediction.get("task"),
            prediction.get("subject_key"),
            prediction.get("as_of_session"),
            prediction.get("horizon_sessions"),
        )
        identity_counts[identity] = identity_counts.get(identity, 0) + 1
    duplicates = [list(k) for k, v in identity_counts.items() if v > 1]

    sessions = [p.get("as_of_session") for p in predictions if p.get("as_of_session")]
    generated = [p.get("generated_at") for p in predictions if p.get("generated_at")]
    clock_errors = [
        {"as_of_session": s, "generated_at": g}
        for s, g in zip(sessions, generated)
        if g is not None and s is not None and str(g)[:10] < str(s)
    ]

    return {
        "distinct_model_keys": model_keys,
        "model_changed_mid_stream": len(model_keys) > 1,
        "requires_new_evidence_epoch": len(model_keys) > 1,
        "duplicate_generation_count": len(duplicates),
        "duplicate_identities": duplicates[:10],
        "clock_error_count": len(clock_errors),
        "clock_errors": clock_errors[:10],
    }


def build_monitoring_report(
    predictions: Sequence[Mapping[str, Any]],
    matured: Sequence[Mapping[str, Any]] = (),
    *,
    predicted_key: str = "predicted",
    actual_key: str = "actual",
    reference_values: Sequence[float] = (),
    current_values: Sequence[float] = (),
) -> dict[str, Any]:
    """Assemble the full doc-10.3 monitoring report.

    Reports only. Doc 10.3: "Monitoring must not retrain or promote a model
    automatically" -- there is deliberately no code path from this
    function's output back into training, registration, or status change.
    """
    coverage = coverage_report(predictions)
    lineage = lineage_consistency(predictions)
    error = realized_error_by_window(
        matured, predicted_key=predicted_key, actual_key=actual_key
    )
    drift = distribution_drift(reference_values, current_values)

    conclusions_supported = bool(
        coverage["sufficient_sample"] and error.get("sufficient_sample")
    )
    return {
        "coverage": coverage,
        "lineage": lineage,
        "realized_error": error,
        "output_drift": drift,
        "conclusions_supported_by_sample_size": conclusions_supported,
        "notes": (
            "Monitoring is read-only: it never retrains, registers, or promotes "
            "a model (strategy doc 10.3). Any status change requires a separate, "
            "explicit human promotion decision."
        ),
    }
