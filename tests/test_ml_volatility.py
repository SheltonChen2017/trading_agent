"""Tests for ml/baselines.py, ml/evaluation.py, and ml/volatility.py (ML-4)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from ml.baselines import (
    BaselineError,
    ewma_volatility_pct,
    no_skill_rank_baseline,
    residual_momentum_score,
    trailing_realized_volatility_pct,
)
from ml.evaluation import (
    EvaluationError,
    EvaluationReport,
    beats_baseline_in_multiple_folds,
    brier_score,
    calibration_curve,
    interval_coverage,
    log_loss,
    mean_absolute_error,
    pinball_loss,
    qlike_loss,
)
from ml.splits import purged_grouped_walk_forward_splits
from ml.volatility import (
    VolatilityForecast,
    VolatilityModelError,
    annualize_pct,
    build_volatility_training_matrix,
    empirical_prediction_interval,
    evaluate_volatility_models,
    fit_gradient_boosted_volatility,
    fit_log_volatility_regression,
    predict_volatility,
    probability_above_ceiling,
    unavailable_forecast,
)


# --- baselines -------------------------------------------------------------


def test_trailing_volatility_matches_manual_std():
    rng = np.random.default_rng(0)
    returns = pd.Series(rng.normal(0, 0.01, 100))
    value = trailing_realized_volatility_pct(returns, window=20)
    expected = float(returns.tail(20).std(ddof=1) * 100)
    assert value == pytest.approx(expected)


def test_trailing_volatility_returns_none_when_too_short():
    assert trailing_realized_volatility_pct(pd.Series([0.01, 0.02]), window=20) is None


def test_baselines_do_not_compress_away_recent_missing_observations():
    values = pd.Series([0.01] * 25 + [np.nan])
    assert trailing_realized_volatility_pct(values, window=20) is None
    assert ewma_volatility_pct(values, min_observations=20) is None


def test_ewma_volatility_reacts_faster_than_trailing_to_a_vol_spike():
    calm = [0.001] * 100
    spike = [0.05, -0.05] * 10
    returns = pd.Series(calm + spike)
    ewma = ewma_volatility_pct(returns, halflife=5.0)
    trailing = trailing_realized_volatility_pct(returns, window=100)
    assert ewma > trailing


def test_baselines_reject_invalid_parameters():
    with pytest.raises(BaselineError):
        trailing_realized_volatility_pct(pd.Series([0.1] * 10), window=1)
    with pytest.raises(BaselineError):
        ewma_volatility_pct(pd.Series([0.1] * 30), halflife=0)
    with pytest.raises(BaselineError):
        no_skill_rank_baseline(0)


def test_no_skill_baseline_is_all_zeros():
    assert np.array_equal(no_skill_rank_baseline(4), np.zeros(4))


def test_residual_momentum_is_positive_when_stock_beats_benchmark():
    n = 300
    index = pd.bdate_range("2024-01-01", periods=n)
    stock = pd.Series(100 * (1.001 ** np.arange(n)), index=index)
    bench = pd.Series(100 * (1.0002 ** np.arange(n)), index=index)
    score = residual_momentum_score(stock, bench)
    assert score is not None and score > 0


def test_residual_momentum_rejects_bad_windows():
    s = pd.Series([100.0] * 300, index=pd.bdate_range("2024-01-01", periods=300))
    with pytest.raises(BaselineError):
        residual_momentum_score(s, s, lookback_sessions=10, skip_sessions=20)


# --- evaluation metrics ----------------------------------------------------


def test_qlike_is_zero_for_a_perfect_forecast_and_positive_otherwise():
    actual = [20.0, 25.0, 30.0]
    assert qlike_loss(actual, actual) == pytest.approx(0.0, abs=1e-12)
    assert qlike_loss(actual, [10.0, 10.0, 10.0]) > 0


def test_qlike_penalizes_under_prediction_more_than_over_prediction():
    actual = [20.0] * 5
    under = qlike_loss(actual, [10.0] * 5)
    over = qlike_loss(actual, [40.0] * 5)
    assert under > over


def test_qlike_rejects_non_positive_predictions_instead_of_improving_coverage():
    with pytest.raises(EvaluationError, match="strictly positive"):
        qlike_loss([20.0, 20.0], [0.0, -5.0])


def test_mean_absolute_error_skips_non_finite_pairs():
    assert mean_absolute_error([1.0, np.nan, 3.0], [2.0, 5.0, 3.0]) == pytest.approx(0.5)


def test_interval_coverage_counts_inclusion():
    assert interval_coverage([1.0, 5.0, 9.0], [0.0, 0.0, 0.0], [10.0, 10.0, 10.0]) == 1.0
    assert interval_coverage([1.0, 50.0], [0.0, 0.0], [10.0, 10.0]) == pytest.approx(0.5)


def test_interval_coverage_rejects_inverted_bounds():
    with pytest.raises(EvaluationError, match="below lower"):
        interval_coverage([1.0], [5.0], [2.0])


def test_brier_and_log_loss_reward_correct_confident_predictions():
    actual = [1, 1, 0, 0]
    good = [0.9, 0.95, 0.05, 0.1]
    bad = [0.1, 0.05, 0.95, 0.9]
    assert brier_score(actual, good) < brier_score(actual, bad)
    assert log_loss(actual, good) < log_loss(actual, bad)


def test_log_loss_is_finite_even_for_a_confidently_wrong_prediction():
    value = log_loss([1], [0.0])
    assert value is not None and math.isfinite(value)


def test_probability_metrics_reject_out_of_range_inputs():
    with pytest.raises(EvaluationError):
        brier_score([1, 0], [1.5, 0.0])
    with pytest.raises(EvaluationError):
        log_loss([2, 0], [0.5, 0.5])


def test_calibration_curve_reports_empty_bins_rather_than_dropping_them():
    rows = calibration_curve([1, 0], [0.95, 0.05], n_bins=10)
    assert len(rows) == 10
    assert any(r["count"] == 0 for r in rows)
    populated = [r for r in rows if r["count"]]
    assert all(r["observed_frequency"] is not None for r in populated)


def test_calibration_curve_rejects_probabilities_outside_unit_interval():
    with pytest.raises(EvaluationError, match="within"):
        calibration_curve([1, 0], [2.0, -1.0])


def test_pinball_loss_is_asymmetric_by_quantile():
    # For a 0.9 quantile, under-predicting is penalized more heavily.
    under = pinball_loss([10.0], [5.0], quantile=0.9)
    over = pinball_loss([10.0], [15.0], quantile=0.9)
    assert under > over


def test_beats_baseline_requires_multiple_folds():
    folds = [
        {"gbm_qlike": 1.0, "ewma_qlike": 2.0},
        {"gbm_qlike": 3.0, "ewma_qlike": 2.0},
    ]
    result = beats_baseline_in_multiple_folds(
        folds, candidate_key="gbm_qlike", baseline_key="ewma_qlike"
    )
    assert result["folds_won"] == 1
    assert not result["passes"]  # one fold is not "more than one"

    winning = [
        {"gbm_qlike": 1.0, "ewma_qlike": 2.0},
        {"gbm_qlike": 1.5, "ewma_qlike": 2.0},
    ]
    assert beats_baseline_in_multiple_folds(
        winning, candidate_key="gbm_qlike", baseline_key="ewma_qlike"
    )["passes"]


def test_beats_baseline_treats_missing_metrics_as_not_comparable():
    folds = [{"gbm_qlike": None, "ewma_qlike": 2.0}, {"gbm_qlike": 1.0, "ewma_qlike": 2.0}]
    result = beats_baseline_in_multiple_folds(
        folds, candidate_key="gbm_qlike", baseline_key="ewma_qlike"
    )
    assert result["comparable_folds"] == 1
    assert not result["passes"]


# --- EvaluationReport contract ---------------------------------------------


def _report(**overrides) -> EvaluationReport:
    kwargs = dict(
        research_question="Can X rank Y?",
        preregistered_primary_outcome="date-level Spearman IC",
        candidate_models=("ridge", "gbm"),
        baselines=("ewma",),
        simultaneous_research_looks=4,
        dataset_hash="a" * 64,
        feature_set_version="fs-v1",
        point_in_time_data=False,
        survivorship_bias_note="fixed universe; current members only",
        split_summary=({"fold_index": 1},),
        entry_timing="next_open",
        cost_tax_capital_assumptions={"transaction_cost_bps": 5},
        fold_metrics=({"fold_index": 1}, {"fold_index": 2}),
        aggregate_metrics={"mean_ic": 0.01},
        dependence_aware_uncertainty={"p_value": 0.3},
        failure_analysis={"worst_year": 2022},
        calibration=({"bin_lower": 0.0},),
        coverage_warnings=(),
        limitations=("exploratory only",),
        verdict="exploratory",
        generated_at="2026-07-31T00:00:00+00:00",
    )
    kwargs.update(overrides)
    return EvaluationReport(**kwargs)


def test_evaluation_report_rejects_an_unknown_verdict():
    with pytest.raises(EvaluationError, match="verdict must be one of"):
        _report(verdict="promoted")


def test_evaluation_report_requires_a_baseline_and_limitations():
    with pytest.raises(EvaluationError, match="frozen baseline"):
        _report(baselines=())
    with pytest.raises(EvaluationError, match="limitations"):
        _report(limitations=())


def test_evaluation_report_blocks_promotion_for_non_point_in_time_data():
    blockers = _report().promotion_blockers()
    assert "not_point_in_time_data" in blockers


def test_evaluation_report_blocks_promotion_with_too_few_folds():
    blockers = _report(fold_metrics=({"fold_index": 1},)).promotion_blockers()
    assert "fewer_than_two_untouched_folds" in blockers


def test_evaluation_report_is_hashed_and_json_serializable():
    import json

    payload = _report().to_dict()
    assert len(payload["report_sha256"]) == 64
    assert payload["production_authoritative"] is False
    json.dumps(payload)


def test_evaluation_report_deep_copies_and_freezes_metric_payloads():
    metrics = {"nested": {"values": [1.0, 2.0]}}
    report = _report(aggregate_metrics=metrics)
    metrics["nested"]["values"].append(999.0)
    assert report.to_dict()["aggregate_metrics"] == {
        "nested": {"values": [1.0, 2.0]}
    }
    with pytest.raises(TypeError):
        report.aggregate_metrics["new"] = 1


# --- volatility models -----------------------------------------------------


def _volatility_frame(n: int = 400, seed: int = 0) -> pd.DataFrame:
    """Synthetic data with a PLANTED relationship: forward vol genuinely
    depends on trailing vol, so a working model should beat a naive one
    (doc 15.2: "a planted volatility relationship should beat a naive
    baseline")."""
    rng = np.random.default_rng(seed)
    sessions = pd.bdate_range("2024-01-01", periods=n)
    trailing = np.abs(rng.normal(20, 6, n)) + 5
    forward = trailing * 0.85 + rng.normal(0, 1.2, n)
    forward = np.clip(forward, 1.0, None)
    return pd.DataFrame(
        {
            "as_of_session": [str(s.date()) for s in sessions],
            "ticker": ["AAA"] * n,
            "exit_session": [str(s.date()) for s in sessions],
            "trailing_vol": trailing,
            "downside_vol": trailing * 0.7,
            "forward_vol": forward,
            "ewma_vol": trailing * 1.05,
        }
    )


def test_annualize_pct_applies_sqrt_of_time():
    assert annualize_pct(1.0) == pytest.approx(math.sqrt(252))


def test_build_training_matrix_returns_ordered_feature_names():
    frame = _volatility_frame(100)
    x, y, ordered = build_volatility_training_matrix(
        frame, feature_columns=["trailing_vol", "downside_vol"], target_column="forward_vol"
    )
    assert ordered == ("trailing_vol", "downside_vol")
    assert x.shape == (100, 2)
    assert y.shape == (100,)


def test_build_training_matrix_rejects_missing_and_duplicate_columns():
    frame = _volatility_frame(50)
    with pytest.raises(VolatilityModelError, match="missing columns"):
        build_volatility_training_matrix(
            frame, feature_columns=["nope"], target_column="forward_vol"
        )
    with pytest.raises(VolatilityModelError, match="duplicates"):
        build_volatility_training_matrix(
            frame, feature_columns=["trailing_vol", "trailing_vol"], target_column="forward_vol"
        )


def test_log_regression_refuses_non_positive_targets():
    x = np.random.default_rng(0).normal(size=(100, 2))
    y = np.array([0.0] * 100)
    with pytest.raises(VolatilityModelError, match="strictly positive"):
        fit_log_volatility_regression(x, y)


def test_models_refuse_thin_training_data():
    x = np.random.default_rng(0).normal(size=(10, 2))
    y = np.abs(np.random.default_rng(1).normal(size=10)) + 1
    with pytest.raises(VolatilityModelError, match="at least"):
        fit_log_volatility_regression(x, y)
    with pytest.raises(VolatilityModelError, match="at least"):
        fit_gradient_boosted_volatility(x, y)


def test_predictions_are_structurally_positive():
    frame = _volatility_frame(300)
    x, y, _ = build_volatility_training_matrix(
        frame, feature_columns=["trailing_vol", "downside_vol"], target_column="forward_vol"
    )
    model = fit_log_volatility_regression(x, y)
    predictions = predict_volatility(model, x)
    assert np.all(predictions > 0)


def test_planted_relationship_is_learned_better_than_a_flat_guess():
    frame = _volatility_frame(400)
    x, y, _ = build_volatility_training_matrix(
        frame, feature_columns=["trailing_vol", "downside_vol"], target_column="forward_vol"
    )
    model = fit_log_volatility_regression(x[:300], y[:300])
    predictions = predict_volatility(model, x[300:])
    flat = np.full(len(y[300:]), float(np.mean(y[:300])))
    assert mean_absolute_error(y[300:], predictions) < mean_absolute_error(y[300:], flat)


def test_evaluate_volatility_models_scores_every_fold_on_untouched_validation():
    frame = _volatility_frame(400)
    folds = purged_grouped_walk_forward_splits(
        list(frame["as_of_session"]), list(frame["exit_session"]),
        n_splits=3, embargo_sessions=5,
    )
    results = evaluate_volatility_models(
        frame, folds,
        feature_columns=["trailing_vol", "downside_vol"],
        target_column="forward_vol",
        trailing_baseline_column="trailing_vol",
        ewma_baseline_column="ewma_vol",
    )
    assert len(results) == 3
    for metrics in results:
        assert metrics["trailing_qlike"] is not None
        assert metrics["ewma_qlike"] is not None
        assert metrics["ridge_qlike"] is not None
        assert metrics["gbm_qlike"] is not None
        assert metrics["validation_row_count"] > 0


def test_model_and_baselines_use_the_same_finite_validation_rows():
    frame = _volatility_frame(250)
    folds = purged_grouped_walk_forward_splits(
        list(frame["as_of_session"]), list(frame["exit_session"]),
        n_splits=2, embargo_sessions=0,
    )
    missing_row = folds[0].validation_row_indices[0]
    frame.loc[missing_row, "ewma_vol"] = np.nan
    results = evaluate_volatility_models(
        frame, folds,
        feature_columns=["trailing_vol", "downside_vol"],
        target_column="forward_vol",
        trailing_baseline_column="trailing_vol",
        ewma_baseline_column="ewma_vol",
    )
    assert results[0]["common_validation_row_count"] == (
        results[0]["validation_row_count"] - 1
    )
    assert results[0]["ridge_qlike"] is not None
    assert results[0]["ewma_qlike"] is not None


def test_thin_fold_records_a_fit_error_rather_than_silently_skipping():
    frame = _volatility_frame(70)
    folds = purged_grouped_walk_forward_splits(
        list(frame["as_of_session"]), list(frame["exit_session"]),
        n_splits=1, embargo_sessions=0,
    )
    results = evaluate_volatility_models(
        frame, folds,
        feature_columns=["trailing_vol"],
        target_column="forward_vol",
        trailing_baseline_column="trailing_vol",
        ewma_baseline_column="ewma_vol",
    )
    assert results[0]["model_fit_error"] is not None
    assert results[0]["ridge_qlike"] is None


def test_empirical_interval_brackets_the_point_forecast():
    errors = np.random.default_rng(0).normal(0, 0.2, 500)
    interval = empirical_prediction_interval(25.0, errors, coverage=0.90)
    assert interval is not None
    lower, upper = interval
    assert lower < 25.0 < upper
    assert lower > 0  # structurally positive, never a negative volatility


def test_empirical_interval_refuses_thin_residual_history():
    assert empirical_prediction_interval(25.0, [0.1] * 5) is None


def test_probability_above_ceiling_moves_the_right_direction():
    errors = np.random.default_rng(0).normal(0, 0.25, 500)
    low = probability_above_ceiling(10.0, errors, ceiling_pct=30.0)
    high = probability_above_ceiling(40.0, errors, ceiling_pct=30.0)
    assert low is not None and high is not None
    assert high > low


def test_unavailable_forecast_requires_a_reason_and_is_never_authoritative():
    with pytest.raises(VolatilityModelError, match="reason"):
        unavailable_forecast(
            subject_key="AAA", horizon_sessions=20, as_of_session="2026-07-31",
            model_key="vol:0.1.0", reasons=[],
        )
    forecast = unavailable_forecast(
        subject_key="AAA", horizon_sessions=20, as_of_session="2026-07-31",
        model_key="vol:0.1.0", reasons=["stale_features"],
    )
    assert not forecast.available
    assert forecast.annualized_volatility_pct is None
    assert forecast.production_authoritative is False


def test_forecast_payload_contains_no_action_field():
    forecast = VolatilityForecast(
        task="volatility_forecast", subject_key="AAA", horizon_sessions=20,
        as_of_session="2026-07-31", annualized_volatility_pct=24.3,
        prediction_interval_pct=(18.1, 33.7), probability_above_mandate_ceiling=0.72,
        model_key="vol:0.1.0", evidence_status="exploratory", available=True,
    )
    payload = forecast.to_dict()
    forbidden = {"side", "shares", "quantity", "order_type", "limit_price",
                 "stop_price", "approved", "execute", "authorization"}
    assert not (forbidden & set(payload))
    assert payload["production_authoritative"] is False
