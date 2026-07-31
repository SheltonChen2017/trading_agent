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

from datetime import date, datetime
import math
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

MIN_OBSERVATIONS_FOR_CONCLUSION = 30
_EASTERN = ZoneInfo("America/New_York")


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


def feature_health_report(predictions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate freshness metadata recorded with every shadow attempt."""
    missing_total = 0
    stale_total = 0
    maximum_ages: list[int] = []
    invalid = 0
    for prediction in predictions:
        freshness = prediction.get("feature_freshness")
        if freshness is None and isinstance(prediction.get("prediction"), Mapping):
            freshness = prediction["prediction"].get("feature_freshness")
        if not isinstance(freshness, Mapping):
            invalid += 1
            continue
        if not freshness:
            invalid += 1
            continue
        aggregate_names = {
            "missing_count", "stale_count", "maximum_age_sessions"
        }
        if aggregate_names <= set(freshness):
            values = tuple(freshness[name] for name in aggregate_names)
            if any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
                for value in values
            ):
                invalid += 1
                continue
            missing_total += int(freshness["missing_count"])
            stale_total += int(freshness["stale_count"])
            maximum_ages.append(int(freshness["maximum_age_sessions"]))
            continue

        # Canonical PredictionRecord also permits per-feature availability
        # dates, e.g. {"realized_vol_20d": "2026-07-30"}.  Missing values
        # are countable; age is reported in calendar days because no exchange
        # calendar/policy threshold is part of this generic monitor.
        missing_total += sum(value is None for value in freshness.values())
        try:
            as_of = date.fromisoformat(str(prediction.get("as_of_session")))
        except ValueError:
            as_of = None
        ages: list[int] = []
        if as_of is not None:
            for value in freshness.values():
                if not isinstance(value, str):
                    continue
                try:
                    available_date = datetime.fromisoformat(
                        value.replace("Z", "+00:00")
                    ).date()
                except ValueError:
                    try:
                        available_date = date.fromisoformat(value)
                    except ValueError:
                        continue
                if available_date > as_of:
                    invalid += 1
                    continue
                ages.append((as_of - available_date).days)
        maximum_ages.append(max(ages) if ages else 0)
    return {
        "prediction_count": len(predictions),
        "valid_freshness_count": len(maximum_ages),
        "invalid_or_missing_freshness_count": invalid,
        "missing_feature_count": missing_total,
        "stale_feature_count": stale_total,
        "maximum_age_sessions": max(maximum_ages) if maximum_ages else None,
        "sufficient_sample": (
            len(predictions) >= MIN_OBSERVATIONS_FOR_CONCLUSION and invalid == 0
        ),
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

    # Internal reference deciles define the buckets, while infinite outer
    # edges ensure a shifted current distribution is fully counted.  Using
    # the reference min/max as histogram bounds silently discarded exactly
    # the out-of-range observations that should create the strongest drift
    # signal.
    quantiles = np.quantile(reference_values, np.linspace(0.1, 0.9, 9))
    internal_edges = np.unique(quantiles)
    edges = np.concatenate(([-np.inf], internal_edges, [np.inf]))
    psi: float | None
    if np.unique(reference_values).size < 2:
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
        try:
            predicted_value, actual_value = float(predicted), float(actual)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(predicted_value) and math.isfinite(actual_value)):
            continue
        raw_session = record.get("as_of_session")
        try:
            parsed_session = date.fromisoformat(str(raw_session))
        except (TypeError, ValueError) as exc:
            raise MonitoringError(
                f"invalid as_of_session in matured outcome: {raw_session!r}"
            ) from exc
        rows.append(
            {
                "as_of_session": parsed_session.isoformat(),
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

    clock_errors: list[dict[str, Any]] = []
    invalid_lineage: list[dict[str, Any]] = []
    for prediction in predictions:
        session_raw = prediction.get("as_of_session")
        generated_raw = prediction.get("generated_at")
        try:
            session = date.fromisoformat(str(session_raw))
            generated_at = datetime.fromisoformat(str(generated_raw).replace("Z", "+00:00"))
            if generated_at.tzinfo is None or generated_at.utcoffset() is None:
                raise ValueError("generated_at is naive")
            generated_session = generated_at.astimezone(_EASTERN).date()
            # Shadow evidence is only prequential if it was generated for
            # that session, not reconstructed days earlier or backfilled
            # after the answer was known.
            if generated_session != session:
                clock_errors.append(
                    {
                        "as_of_session": session.isoformat(),
                        "generated_at": generated_at.isoformat(),
                    }
                )
        except (TypeError, ValueError) as exc:
            clock_errors.append(
                {
                    "as_of_session": session_raw,
                    "generated_at": generated_raw,
                    "reason": str(exc),
                }
            )

        snapshot_hash = prediction.get("feature_snapshot_hash")
        if (
            not isinstance(snapshot_hash, str)
            or len(snapshot_hash) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in snapshot_hash)
        ):
            invalid_lineage.append(
                {
                    "prediction_id": prediction.get("prediction_id"),
                    "reason": "missing_or_invalid_feature_snapshot_hash",
                }
            )

    return {
        "distinct_model_keys": model_keys,
        "model_changed_mid_stream": len(model_keys) > 1,
        "requires_new_evidence_epoch": len(model_keys) > 1,
        "duplicate_generation_count": len(duplicates),
        "duplicate_identities": duplicates[:10],
        "clock_error_count": len(clock_errors),
        "clock_errors": clock_errors[:10],
        "invalid_lineage_count": len(invalid_lineage),
        "invalid_lineage": invalid_lineage[:10],
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
    feature_health = feature_health_report(predictions)
    lineage = lineage_consistency(predictions)
    error = realized_error_by_window(
        matured, predicted_key=predicted_key, actual_key=actual_key
    )
    drift = distribution_drift(reference_values, current_values)

    drift_requested = len(reference_values) > 0 or len(current_values) > 0
    conclusions_supported = bool(
        coverage["sufficient_sample"]
        and feature_health["sufficient_sample"]
        and error.get("sufficient_sample")
        and (not drift_requested or drift.get("sufficient_sample"))
        and not lineage["requires_new_evidence_epoch"]
        and lineage["clock_error_count"] == 0
        and lineage["invalid_lineage_count"] == 0
    )
    return {
        "coverage": coverage,
        "feature_health": feature_health,
        "lineage": lineage,
        "realized_error": error,
        "output_drift": drift,
        "conclusions_supported_by_sample_size": conclusions_supported,
        "production_authoritative": False,
        "notes": (
            "Monitoring is read-only: it never retrains, registers, or promotes "
            "a model (strategy doc 10.3). Any status change requires a separate, "
            "explicit human promotion decision."
        ),
    }
