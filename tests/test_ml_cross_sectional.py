"""Tests for ml/cross_sectional.py (ML-7) and the date-level evaluation
metrics it relies on. Includes doc 15.2's required synthetic checks: pure
noise must not produce apparent skill, and same-day rows must not be
treated as independent time observations."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.cross_sectional import (
    RankerError,
    RankerObservation,
    block_bootstrap_ic_significance,
    build_ranker_observations,
    count_research_looks,
    evaluate_ranker_fold,
    fit_elastic_net_ranker,
    fit_gradient_boosted_ranker,
)
from ml.evaluation import (
    EvaluationError,
    date_level_spearman_ic,
    summarize_information_coefficient,
    top_minus_bottom_quantile_spread,
)


def _panel(n_dates: int = 60, n_names: int = 10, *, skill: float = 0.0, seed: int = 0):
    """A (date, ticker) panel where `skill` controls how much the score
    genuinely predicts the outcome. skill=0 is pure noise."""
    rng = np.random.default_rng(seed)
    rows = []
    dates = pd.bdate_range("2026-01-01", periods=n_dates)
    for date in dates:
        scores = rng.normal(size=n_names)
        noise = rng.normal(size=n_names)
        outcomes = skill * scores + noise
        for i in range(n_names):
            rows.append(
                {
                    "as_of_session": str(date.date()),
                    "ticker": f"T{i}",
                    "score": float(scores[i]),
                    "outcome": float(outcomes[i]),
                }
            )
    return pd.DataFrame(rows)


# --- research-look counting (doc 11.1/11.4) --------------------------------


def test_research_looks_multiply_across_every_dimension():
    looks = count_research_looks(
        models=["a", "b"], labels=["l1"], benchmarks=["QQQ", "SOXX"],
        horizons=[5, 20], feature_families=["f1"],
    )
    assert looks["total_research_looks"] == 8  # 2 * 1 * 2 * 2 * 1
    # Bonferroni threshold tightens as looks grow.
    assert looks["bonferroni_alpha_threshold"] == pytest.approx(0.05 / 8)


def test_more_looks_means_a_stricter_threshold():
    few = count_research_looks(
        models=["a"], labels=["l"], benchmarks=["QQQ"], horizons=[20], feature_families=["f"]
    )
    many = count_research_looks(
        models=["a", "b", "c"], labels=["l"], benchmarks=["QQQ", "SOXX"],
        horizons=[5, 10, 20], feature_families=["f"],
    )
    assert many["bonferroni_alpha_threshold"] < few["bonferroni_alpha_threshold"]


def test_research_looks_rejects_an_empty_dimension():
    with pytest.raises(RankerError, match="at least one"):
        count_research_looks(
            models=[], labels=["l"], benchmarks=["QQQ"], horizons=[20], feature_families=["f"]
        )


# --- date-level IC ---------------------------------------------------------


def test_ic_is_near_zero_for_pure_noise():
    """Doc 15.2: 'pure noise must not produce persistent out-of-sample alpha.'"""
    panel = _panel(skill=0.0, seed=1)
    ic = date_level_spearman_ic(panel, score_column="score", outcome_column="outcome")
    summary = summarize_information_coefficient(ic)
    assert abs(summary["mean_ic"]) < 0.10
    assert 0.3 < summary["positive_date_fraction"] < 0.7


def test_ic_is_strongly_positive_when_skill_is_planted():
    panel = _panel(skill=3.0, seed=2)
    ic = date_level_spearman_ic(panel, score_column="score", outcome_column="outcome")
    summary = summarize_information_coefficient(ic)
    assert summary["mean_ic"] > 0.5
    assert summary["positive_date_fraction"] > 0.9


def test_ic_is_computed_per_date_not_pooled():
    panel = _panel(n_dates=30, skill=1.0, seed=3)
    ic = date_level_spearman_ic(panel, score_column="score", outcome_column="outcome")
    # One IC per date -- never a single pooled number over all rows.
    assert len(ic) == 30


def test_dates_with_too_few_names_are_dropped_not_averaged_in():
    panel = _panel(n_dates=5, n_names=10, seed=4)
    thin = panel[panel["as_of_session"] == panel["as_of_session"].iloc[0]].head(3)
    combined = pd.concat([panel[panel["as_of_session"] != panel["as_of_session"].iloc[0]], thin])
    ic = date_level_spearman_ic(
        combined, score_column="score", outcome_column="outcome", min_names_per_date=5
    )
    assert panel["as_of_session"].iloc[0] not in ic.index


def test_ic_summary_reports_sign_consistency_not_just_the_mean():
    # Two signals with a similar mean IC but very different consistency.
    steady = pd.Series([0.05] * 20)
    erratic = pd.Series([0.55, -0.45] * 10)
    steady_summary = summarize_information_coefficient(steady)
    erratic_summary = summarize_information_coefficient(erratic)
    assert steady_summary["positive_date_fraction"] == 1.0
    assert erratic_summary["positive_date_fraction"] == 0.5
    assert steady_summary["information_ratio"] is None or steady_summary["std_ic"] == 0.0
    assert erratic_summary["std_ic"] > steady_summary["std_ic"]


def test_ic_summary_handles_an_empty_series():
    summary = summarize_information_coefficient(pd.Series(dtype=float))
    assert summary["date_count"] == 0
    assert summary["mean_ic"] is None


def test_quantile_spread_is_positive_only_when_skill_exists():
    skilled = top_minus_bottom_quantile_spread(
        _panel(skill=3.0, seed=5), score_column="score", outcome_column="outcome"
    )
    noise = top_minus_bottom_quantile_spread(
        _panel(skill=0.0, seed=6), score_column="score", outcome_column="outcome"
    )
    assert skilled["mean_spread"] > noise["mean_spread"]
    assert skilled["positive_date_fraction"] > 0.9


# --- same-day independence (doc 15.2) --------------------------------------


def test_duplicate_date_ticker_rows_are_rejected_not_counted_twice():
    """Doc 15.2: 'duplicate same-day cross-sectional rows must not be
    treated as independent time observations.' Date-level IC collapses each
    session to ONE observation, so tripling the names on a day cannot
    triple the apparent sample size."""
    panel = _panel(n_dates=20, n_names=10, seed=7)
    duplicated = pd.concat([panel, panel.iloc[[0]]], ignore_index=True)
    with pytest.raises(EvaluationError, match="duplicate"):
        date_level_spearman_ic(
            duplicated, score_column="score", outcome_column="outcome"
        )


# --- significance delegation ------------------------------------------------


def test_block_bootstrap_delegates_to_the_existing_project_toolkit():
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2026-01-01", periods=240)
    ic = pd.Series(rng.normal(0, 0.1, 240), index=[str(d.date()) for d in dates])
    result = block_bootstrap_ic_significance(ic, block_length=20, n_bootstrap=200, seed=0)
    assert result["available"]
    assert result["block_length"] == 20
    # The delegated function's own keys come through rather than being
    # re-derived here.
    assert "p_value" in result


def test_block_bootstrap_is_unavailable_for_empty_input():
    result = block_bootstrap_ic_significance(pd.Series(dtype=float), block_length=5)
    assert not result["available"]


def test_block_bootstrap_propagates_a_thin_sample_refusal():
    result = block_bootstrap_ic_significance(
        pd.Series([0.1, -0.1], index=["2026-01-01", "2026-01-02"]),
        block_length=2,
        n_bootstrap=20,
    )
    assert not result["available"]
    assert result["reason"]


# --- model fits -------------------------------------------------------------


def test_ranker_models_refuse_thin_pooled_training_data():
    x = np.random.default_rng(0).normal(size=(50, 3))
    y = np.random.default_rng(1).normal(size=50)
    with pytest.raises(RankerError, match="pooled training rows"):
        fit_elastic_net_ranker(x, y)
    with pytest.raises(RankerError, match="pooled training rows"):
        fit_gradient_boosted_ranker(x, y)


def test_elastic_net_learns_a_planted_linear_relationship():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(400, 3))
    y = 2.0 * x[:, 0] + rng.normal(0, 0.1, 400)
    model = fit_elastic_net_ranker(x, y, alpha=0.001)
    # The informative feature should carry the largest coefficient.
    assert abs(model.coef_[0]) > abs(model.coef_[1])
    assert abs(model.coef_[0]) > abs(model.coef_[2])


def test_gradient_boosted_ranker_fits_and_predicts():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(400, 3))
    y = 2.0 * x[:, 0] + rng.normal(0, 0.1, 400)
    model = fit_gradient_boosted_ranker(x, y, max_iter=30)
    predictions = model.predict(x)
    assert predictions.shape == (400,)
    assert np.isfinite(predictions).all()


# --- fold evaluation and observations ---------------------------------------


def test_evaluate_ranker_fold_returns_ic_and_spread():
    panel = _panel(skill=2.0, seed=8)
    result = evaluate_ranker_fold(panel, score_column="score", outcome_column="outcome")
    assert result["information_coefficient"]["mean_ic"] > 0.3
    assert result["quantile_spread"]["mean_spread"] > 0
    assert len(result["ic_by_date"]) > 0


def test_ranker_observations_carry_no_action_field_and_no_authority():
    panel = _panel(n_dates=3, n_names=5, seed=9)
    observations = build_ranker_observations(
        panel, score_column="score", model_key="tech-ranker:0.1.0", horizon_sessions=20
    )
    assert len(observations) == 15
    payload = observations[0].to_dict()
    forbidden = {"side", "shares", "quantity", "order_type", "limit_price",
                 "stop_price", "approved", "execute", "authorization"}
    assert not (forbidden & set(payload))
    assert payload["production_authoritative"] is False
    assert payload["evidence_status"] == "exploratory"


def test_ranker_observations_report_uncertainty_not_fabricated_confidence():
    panel = _panel(n_dates=2, n_names=5, seed=10)
    observations = build_ranker_observations(
        panel, score_column="score", model_key="m", horizon_sessions=20
    )
    # Doc 16 forbids presenting raw model output as calibrated confidence.
    assert all(o.uncertainty == "high" for o in observations)
    assert all(o.probability_positive_excess is None for o in observations)


def test_ranker_observation_percentiles_are_within_unit_range():
    panel = _panel(n_dates=4, n_names=8, seed=11)
    observations = build_ranker_observations(
        panel, score_column="score", model_key="m", horizon_sessions=20
    )
    percentiles = [o.cross_sectional_percentile for o in observations]
    assert all(0 < p <= 1 for p in percentiles)


def test_build_observations_rejects_a_missing_column():
    panel = _panel(n_dates=2, n_names=5)
    with pytest.raises(RankerError, match="missing column"):
        build_ranker_observations(
            panel, score_column="nope", model_key="m", horizon_sessions=20
        )
