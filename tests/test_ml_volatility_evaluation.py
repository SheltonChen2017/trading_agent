"""Tests for ml/volatility_evaluation.py (ML-LR-3 sections 9.4/9.5),
covering the remaining plan 9.6 items: intervals use only residuals
available before the prediction date; a crisis-only aggregate win fails
multi-fold stability; and a probability is never labeled confidence until
calibration clears its preregistered gate.
"""
from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd
import pytest

from ml.volatility_evaluation import (
    CalibrationStatus,
    ShadowVolatilityForecast,
    VolatilityEvaluationError,
    aggregate_interval_coverage,
    evaluate_by_slice,
    evaluate_ceiling_calibration,
    evaluate_warning_behavior,
    expanding_out_of_fold_intervals,
)


def _fold(index: int, n: int = 60, *, seed: int = 0, bias: float = 0.0):
    rng = np.random.default_rng(seed + index)
    predicted = np.abs(rng.normal(20, 4, n)) + 5
    actual = predicted * np.exp(rng.normal(bias, 0.25, n))
    return {"fold_index": index, "actual": actual, "predicted": predicted}


# --- prediction intervals: the leakage rule ---------------------------------


def test_the_first_fold_gets_no_interval_because_no_prior_residuals_exist():
    """Plan 9.6: 'intervals use only residuals available before the
    prediction date.' Fold 0 has nothing prior, so it must report
    unavailable rather than silently borrowing later data."""
    results = expanding_out_of_fold_intervals([_fold(0), _fold(1), _fold(2)])
    assert results[0]["interval_available"] is False
    assert results[0]["prior_residual_count"] == 0
    assert "no prior out-of-fold residuals" in results[0]["reason"]


def test_later_folds_use_only_earlier_residuals():
    folds = [_fold(0, n=60), _fold(1, n=60), _fold(2, n=60)]
    results = expanding_out_of_fold_intervals(folds)
    # Fold 1 sees exactly fold 0's residuals; fold 2 sees folds 0+1.
    assert results[1]["prior_residual_count"] == 60
    assert results[2]["prior_residual_count"] == 120


def test_a_folds_own_residuals_never_inform_its_own_interval():
    """The decisive test. Corrupting ONLY the last fold's actuals must not
    change that fold's interval bounds -- if it did, the fold would be
    calibrating on the outcomes it is scored against."""
    folds = [_fold(0), _fold(1), _fold(2)]
    baseline = expanding_out_of_fold_intervals(folds)

    corrupted = [dict(f) for f in folds]
    corrupted[2] = dict(corrupted[2])
    corrupted[2]["actual"] = corrupted[2]["actual"] * 5.0  # wildly different
    after = expanding_out_of_fold_intervals(corrupted)

    assert baseline[2]["log_residual_quantiles"] == after[2]["log_residual_quantiles"]
    # Coverage legitimately changes, because the outcomes changed.
    assert baseline[2]["coverage"] != after[2]["coverage"]


def test_a_thin_prior_history_reports_unavailable_rather_than_a_wide_guess():
    folds = [_fold(0, n=5), _fold(1, n=60)]
    results = expanding_out_of_fold_intervals(folds, minimum_residuals=20)
    assert results[1]["interval_available"] is False
    assert "only 5 prior residuals" in results[1]["reason"]


def test_interval_coverage_is_near_the_target_for_a_well_behaved_model():
    folds = [_fold(i, n=200, seed=7) for i in range(4)]
    results = expanding_out_of_fold_intervals(folds, coverage=0.90)
    covered = [f["coverage"] for f in results if f["interval_available"]]
    assert covered
    assert all(0.75 <= c <= 1.0 for c in covered)


def test_interval_bounds_are_strictly_positive():
    folds = [_fold(0), _fold(1)]
    results = expanding_out_of_fold_intervals(folds)
    # Log-scale residuals guarantee positivity structurally.
    low, high = results[1]["log_residual_quantiles"]
    assert math.exp(low) > 0 and math.exp(high) > 0
    assert results[1]["mean_interval_width_pct"] > 0


def test_aggregate_coverage_ignores_folds_without_intervals():
    folds = [_fold(i) for i in range(3)]
    results = expanding_out_of_fold_intervals(folds)
    aggregate = aggregate_interval_coverage(results)
    assert aggregate["folds_with_intervals"] == 2
    assert 0 <= aggregate["aggregate_coverage"] <= 1


def test_aggregate_coverage_handles_no_intervals():
    aggregate = aggregate_interval_coverage([{"interval_available": False}])
    assert aggregate["folds_with_intervals"] == 0
    assert aggregate["aggregate_coverage"] is None


def test_invalid_coverage_is_refused():
    with pytest.raises(VolatilityEvaluationError, match="coverage must be"):
        expanding_out_of_fold_intervals([_fold(0)], coverage=1.5)


# --- ceiling calibration ----------------------------------------------------


def _calibration_sample(n: int = 400, *, seed: int = 0, skill: bool = True):
    rng = np.random.default_rng(seed)
    actual = np.abs(rng.normal(20, 8, n)) + 2
    if skill:
        # Probability tracks the truth, with noise.
        probability = np.clip((actual - 15) / 20 + rng.normal(0, 0.08, n), 0.01, 0.99)
    else:
        probability = np.full(n, 0.5)
    return actual, probability


def test_calibration_is_experimental_without_a_preregistered_bar():
    """Plan 9.5: 'If calibration has not cleared its preregistered gate,
    serialize the probability as experimental and never label it
    confidence.'"""
    actual, probability = _calibration_sample()
    result = evaluate_ceiling_calibration(actual, probability, ceiling_pct=25.0)
    assert result["calibration_status"] == CalibrationStatus.EXPERIMENTAL
    assert "must not be labeled confidence" in result["calibration_note"]


def test_calibration_passes_only_when_it_clears_the_preregistered_bar():
    actual, probability = _calibration_sample()
    good = evaluate_ceiling_calibration(
        actual, probability, ceiling_pct=25.0, maximum_brier=0.5
    )
    assert good["calibration_status"] == CalibrationStatus.CALIBRATED

    strict = evaluate_ceiling_calibration(
        actual, probability, ceiling_pct=25.0, maximum_brier=0.001
    )
    assert strict["calibration_status"] == CalibrationStatus.EXPERIMENTAL


def test_a_single_class_outcome_is_not_measured_rather_than_perfect():
    """A model can score a perfect Brier by always predicting the only
    outcome that ever occurred; that is not calibration."""
    actual = np.full(200, 5.0)  # never breaches a 25% ceiling
    probability = np.zeros(200)
    result = evaluate_ceiling_calibration(actual, probability, ceiling_pct=25.0)
    assert result["calibration_status"] == CalibrationStatus.NOT_MEASURED
    assert result["brier_score"] is None
    assert "both classes required" in result["insufficiency_reason"]


def test_a_thin_sample_is_not_measured():
    actual, probability = _calibration_sample(n=10)
    result = evaluate_ceiling_calibration(actual, probability, ceiling_pct=25.0)
    assert result["calibration_status"] == CalibrationStatus.NOT_MEASURED


def test_calibration_reports_the_breach_rate_and_curve():
    actual, probability = _calibration_sample()
    result = evaluate_ceiling_calibration(
        actual, probability, ceiling_pct=25.0, maximum_brier=0.5
    )
    assert 0 < result["breach_rate"] < 1
    assert len(result["calibration"]) == 10


def test_a_non_positive_ceiling_is_refused():
    with pytest.raises(VolatilityEvaluationError, match="ceiling_pct"):
        evaluate_ceiling_calibration([1.0], [0.5], ceiling_pct=0.0)


# --- warning behavior -------------------------------------------------------


def _warning_frame():
    """A calm stretch, then a breach episode. The model anticipates it two
    sessions early; trailing volatility only reacts once it has begun."""
    sessions = [f"2026-01-{d:02d}" for d in range(1, 21)]
    actual = [10.0] * 12 + [30.0] * 4 + [10.0] * 4
    model = [10.0] * 10 + [30.0] * 6 + [10.0] * 4
    trailing = [10.0] * 12 + [30.0] * 4 + [10.0] * 4
    return pd.DataFrame({
        "as_of_session": sessions,
        "actual": actual,
        "model_predicted": model,
        "trailing_predicted": trailing,
    })


def test_warning_lead_time_credits_an_earlier_warning():
    result = evaluate_warning_behavior(_warning_frame(), ceiling_pct=25.0)
    assert result["breach_episode_count"] == 1
    assert result["model"]["mean_lead_sessions"] == 2
    assert result["trailing"]["mean_lead_sessions"] == 0
    assert result["model_warns_earlier_than_trailing"] is True


def test_false_warning_rate_is_reported_for_both():
    result = evaluate_warning_behavior(_warning_frame(), ceiling_pct=25.0)
    # The model warns on 2 non-breach sessions; trailing warns on none.
    assert result["model"]["false_warning_count"] == 2
    assert result["trailing"]["false_warning_count"] == 0
    assert result["model"]["false_warning_rate"] > 0


def test_a_model_that_never_warns_earlier_gets_no_credit():
    frame = _warning_frame()
    frame["model_predicted"] = frame["trailing_predicted"]
    result = evaluate_warning_behavior(frame, ceiling_pct=25.0)
    assert result["model_warns_earlier_than_trailing"] is False


def test_warning_episodes_are_not_interleaved_across_tickers():
    """A calm ticker must not split a different ticker's contiguous crisis."""
    rows = []
    sessions = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]
    for index, session in enumerate(sessions):
        rows.extend(
            (
                {
                    "ticker": "AAA", "as_of_session": session,
                    "actual": (10, 10, 30, 30)[index],
                    "model_predicted": (10, 30, 30, 30)[index],
                    "trailing_predicted": (10, 10, 30, 30)[index],
                },
                {
                    "ticker": "BBB", "as_of_session": session,
                    "actual": 10, "model_predicted": 10, "trailing_predicted": 10,
                },
            )
        )
    result = evaluate_warning_behavior(pd.DataFrame(rows), ceiling_pct=25.0)
    assert result["breach_episode_count"] == 1
    assert result["per_subject"]["AAA"]["model"]["mean_lead_sessions"] == 1
    assert result["model_warns_earlier_than_trailing"] is True


def test_warning_behavior_requires_its_columns():
    with pytest.raises(VolatilityEvaluationError, match="missing column"):
        evaluate_warning_behavior(pd.DataFrame({"a": [1]}), ceiling_pct=25.0)


# --- slices: the crisis-window test -----------------------------------------


def _slice_frame(n_per_year: int = 60, *, crisis_only: bool):
    """If `crisis_only`, the model beats the baseline in 2022 alone and is
    no better elsewhere -- doc 8.3's "small aggregate win produced by one
    crisis window"."""
    rng = np.random.default_rng(0)
    rows = []
    for year in (2021, 2022, 2023, 2024):
        for i in range(n_per_year):
            actual = float(abs(rng.normal(20, 5)) + 5)
            baseline = actual * float(np.exp(rng.normal(0, 0.25)))
            if crisis_only and year != 2022:
                # Outside the crisis window the model must be clearly WORSE
                # than the baseline, not a near-copy of it. A near-copy wins
                # roughly half the buckets on a coin flip, which would make
                # this test pass or fail on the seed rather than on the
                # crisis-only pattern it claims to detect.
                model = actual * float(np.exp(rng.normal(0, 0.60)))
            else:
                model = actual * float(np.exp(rng.normal(0, 0.08)))
            rows.append({
                "year": year, "ticker": f"T{i % 3}",
                "volatility_regime": "high" if actual > 22 else "low",
                "earnings_proximity": "near" if i % 5 == 0 else "far",
                "actual": actual, "model_predicted": model, "ewma_predicted": baseline,
            })
    return pd.DataFrame(rows)


def test_a_crisis_only_win_is_visible_as_a_low_win_fraction():
    """Plan 9.6: 'a crisis-only aggregate win fails multi-fold stability.'
    The slice report is what makes that visible instead of hidden inside a
    favorable aggregate."""
    crisis = evaluate_by_slice(_slice_frame(crisis_only=True))
    broad = evaluate_by_slice(_slice_frame(crisis_only=False))
    assert crisis["year"]["win_fraction"] < broad["year"]["win_fraction"]
    assert crisis["year"]["buckets_won"] <= 2
    assert broad["year"]["buckets_won"] == broad["year"]["sufficient_bucket_count"]


def test_every_requested_slice_is_reported():
    result = evaluate_by_slice(_slice_frame(crisis_only=False))
    assert set(result) == {"year", "ticker", "volatility_regime", "earnings_proximity"}
    assert all(result[k]["available"] for k in result)


def test_a_missing_slice_column_is_reported_not_silently_skipped():
    frame = _slice_frame(crisis_only=False).drop(columns=["earnings_proximity"])
    result = evaluate_by_slice(frame)
    assert result["earnings_proximity"]["available"] is False


def test_a_thin_bucket_is_marked_insufficient_rather_than_dropped():
    frame = _slice_frame(n_per_year=5, crisis_only=False)
    result = evaluate_by_slice(frame, minimum_rows=20)
    buckets = result["year"]["buckets"]
    assert buckets and all(b["sufficient"] is False for b in buckets)
    assert all("usable rows" in b["reason"] for b in buckets)


# --- typed shadow forecast (plan 9.5) ---------------------------------------


def _forecast(**overrides) -> ShadowVolatilityForecast:
    payload = dict(
        task="volatility_forecast",
        subject_key="NVDA",
        model_key="vol:0.1.0",
        artifact_hash="a" * 64,
        as_of_session="2026-07-31",
        target_available_at="2026-08-28T20:00:00+00:00",
        horizon_sessions=20,
        daily_volatility_pct=1.8,
        prediction_interval_daily_pct=(1.2, 2.7),
        probability_above_ceiling=0.72,
        calibration_status=CalibrationStatus.EXPERIMENTAL,
        trailing_baseline_daily_pct=1.7,
        ewma_baseline_daily_pct=1.75,
        feature_freshness={"maximum_age_sessions": 0, "missing_count": 0},
        evidence_status="exploratory",
        available=True,
    )
    payload.update(overrides)
    return ShadowVolatilityForecast(**payload)


def test_an_uncalibrated_probability_is_never_labeled_confidence():
    payload = _forecast().to_dict()
    assert "experimental_probability" in payload
    assert "confidence" not in str(payload).lower()


def test_a_calibrated_probability_gets_the_calibrated_label():
    payload = _forecast(calibration_status=CalibrationStatus.CALIBRATED).to_dict()
    assert "calibrated_probability" in payload
    assert "experimental_probability" not in payload


def test_the_forecast_carries_every_plan_95_field():
    payload = _forecast().to_dict()
    for field in (
        "task", "subject_key", "model_key", "artifact_hash", "as_of_session",
        "target_available_at", "horizon_sessions", "daily_volatility_pct",
        "annualized_volatility_pct", "prediction_interval_daily_pct",
        "calibration_status", "trailing_baseline_daily_pct",
        "ewma_baseline_daily_pct", "feature_freshness", "evidence_status",
        "production_authoritative", "what_this_does_not_mean",
    ):
        assert field in payload, field


def test_the_forecast_is_never_authoritative_and_says_what_it_does_not_mean():
    payload = _forecast().to_dict()
    assert payload["production_authoritative"] is False
    assert "not a recommendation" in payload["what_this_does_not_mean"]
    assert "not used by the execution gate" in payload["what_this_does_not_mean"]


def test_daily_and_annualized_units_are_separately_named():
    forecast = _forecast()
    assert forecast.annualized_volatility_pct == pytest.approx(
        forecast.daily_volatility_pct * math.sqrt(252)
    )
    payload = forecast.to_dict()
    assert "volatility_pct" not in payload  # no ambiguous unlabeled key


def test_an_unavailable_forecast_requires_a_reason_and_carries_no_estimate():
    with pytest.raises(VolatilityEvaluationError, match="at least one refusal reason"):
        _forecast(available=False, daily_volatility_pct=None)
    forecast = _forecast(
        available=False, daily_volatility_pct=None,
        prediction_interval_daily_pct=None, probability_above_ceiling=None,
        refusal_reasons=("stale_features",),
    )
    assert forecast.to_dict()["daily_volatility_pct"] is None


def test_an_available_forecast_cannot_carry_refusal_reasons():
    with pytest.raises(VolatilityEvaluationError, match="cannot carry refusal"):
        _forecast(refusal_reasons=("x",))


def test_an_unknown_calibration_status_is_refused():
    with pytest.raises(VolatilityEvaluationError, match="calibration_status"):
        _forecast(calibration_status="looks_fine")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("task", "ranker", "task must"),
        ("artifact_hash", "not-a-hash", "SHA-256"),
        ("as_of_session", "31-07-2026", "canonical"),
        ("target_available_at", "2026-08-28T20:00:00", "timezone-aware"),
        ("horizon_sessions", 0, "positive integer"),
        ("evidence_status", "approved", "non-authoritative"),
        ("prediction_interval_daily_pct", (3.0, 1.0), "contain the point"),
        ("probability_above_ceiling", 1.1, "within [0, 1]"),
    ),
)
def test_shadow_forecast_rejects_invalid_identity_and_numeric_values(field, value, message):
    with pytest.raises(VolatilityEvaluationError, match=re.escape(message)):
        _forecast(**{field: value})


def test_an_unavailable_forecast_cannot_carry_a_numeric_prediction():
    with pytest.raises(VolatilityEvaluationError, match="cannot carry numeric"):
        _forecast(available=False, refusal_reasons=("stale_features",))


def test_forecast_is_json_serializable():
    import json

    json.dumps(_forecast().to_dict())
