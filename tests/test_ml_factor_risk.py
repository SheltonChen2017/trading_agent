"""Tests for ml/factor_risk.py -- strategy doc 7.3's own test list."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml.factor_risk import (
    FactorRiskError,
    compute_factor_concentration_report,
)


def _index(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2024-01-01", periods=n)


def _prices_from_returns(returns: np.ndarray, index: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(100.0 * np.cumprod(1.0 + returns), index=index)


def _shared_factor_universe(n: int = 300, seed: int = 0):
    """Three 'semiconductor' names driven by one strong shared factor, plus
    two genuinely independent names."""
    rng = np.random.default_rng(seed)
    index = _index(n)
    factor = rng.normal(0, 0.02, n)
    data = {}
    for ticker in ("SEMI1", "SEMI2", "SEMI3"):
        idiosyncratic = rng.normal(0, 0.004, n)
        data[ticker] = _prices_from_returns(factor + idiosyncratic, index)
    for ticker in ("INDEP1", "INDEP2"):
        data[ticker] = _prices_from_returns(rng.normal(0, 0.02, n), index)
    return data


def _independent_universe(n: int = 300, seed: int = 7):
    rng = np.random.default_rng(seed)
    index = _index(n)
    return {
        f"IND{i}": _prices_from_returns(rng.normal(0, 0.02, n), index)
        for i in range(5)
    }


def _equal_weights(data) -> dict[str, float]:
    return {ticker: 1.0 / len(data) for ticker in data}


def test_synthetic_shared_semiconductor_factor_is_recovered():
    data = _shared_factor_universe()
    report = compute_factor_concentration_report(data, _equal_weights(data))

    assert report.available
    # Factor 1 must dominate and must load the three shared names much more
    # heavily than the two independent ones.
    assert report.explained_variance_ratio[0] > 0.4
    factor_1 = report.loadings["Factor 1"]
    semi_loading = np.mean([abs(factor_1[t]) for t in ("SEMI1", "SEMI2", "SEMI3")])
    indep_loading = np.mean([abs(factor_1[t]) for t in ("INDEP1", "INDEP2")])
    assert semi_loading > 3 * indep_loading


def test_independent_assets_do_not_collapse_into_one_concentrated_factor():
    data = _independent_universe()
    report = compute_factor_concentration_report(data, _equal_weights(data))

    assert report.available
    # With 5 independent names, no single factor should dominate, and the
    # effective-independent-bets count should be close to the true 5.
    assert report.explained_variance_ratio[0] < 0.45
    assert report.effective_independent_bets > 3.5


def test_effective_bets_is_lower_for_a_concentrated_book_than_a_diversified_one():
    concentrated = _shared_factor_universe()
    diversified = _independent_universe()

    concentrated_report = compute_factor_concentration_report(
        concentrated, _equal_weights(concentrated)
    )
    diversified_report = compute_factor_concentration_report(
        diversified, _equal_weights(diversified)
    )

    assert (
        concentrated_report.effective_independent_bets
        < diversified_report.effective_independent_bets
    )


def test_constant_series_fails_safely_rather_than_dividing_by_zero():
    data = _independent_universe()
    index = _index(300)
    data["FLAT"] = pd.Series([100.0] * 300, index=index)

    report = compute_factor_concentration_report(data, _equal_weights(data))

    assert not report.available
    assert "constant or zero-variance" in report.unavailable_reason
    # Never a silently-successful report with NaN loadings.
    assert report.loadings == {}


def test_duplicate_series_still_produces_a_finite_report():
    data = _independent_universe()
    data["DUP"] = data["IND0"].copy()

    report = compute_factor_concentration_report(data, _equal_weights(data))

    assert report.available
    for factor_loadings in report.loadings.values():
        assert all(np.isfinite(v) for v in factor_loadings.values())


def test_mismatched_histories_are_aligned_before_calculation():
    n = 300
    data = _independent_universe(n)
    # One name starts 100 sessions late -- alignment must intersect, not
    # backfill.
    data["LATE"] = data["IND0"].iloc[100:].copy()

    report = compute_factor_concentration_report(data, _equal_weights(data))

    assert report.available
    assert report.common_observation_count <= n - 100


def test_missing_history_is_surfaced_not_treated_as_zero_exposure():
    data = _independent_universe()
    index = _index(300)
    data["NOHIST"] = pd.Series([np.nan] * 300, index=index)

    report = compute_factor_concentration_report(data, _equal_weights(data))

    assert "NOHIST" in report.missing_tickers
    assert "NOHIST" not in report.tickers
    assert any("NOHIST" in w for w in report.warnings)


def test_non_finite_returns_never_produce_a_successful_report():
    data = _independent_universe()
    # A zero price creates an infinite pct_change on the next session.
    data["IND0"].iloc[50] = 0.0

    report = compute_factor_concentration_report(data, _equal_weights(data))

    # Either the bad row is sanitized out (still available, finite) or the
    # report refuses -- never a successful report containing inf/NaN.
    if report.available:
        for factor_loadings in report.loadings.values():
            assert all(np.isfinite(v) for v in factor_loadings.values())


def test_results_are_invariant_to_input_ticker_order():
    data = _shared_factor_universe()
    reversed_data = {k: data[k] for k in reversed(list(data))}

    first = compute_factor_concentration_report(data, _equal_weights(data))
    second = compute_factor_concentration_report(
        reversed_data, _equal_weights(reversed_data)
    )

    assert first.tickers == second.tickers  # display order is sorted, not input order
    assert first.explained_variance_ratio == second.explained_variance_ratio
    assert first.loadings == second.loadings
    assert first.effective_independent_bets == second.effective_independent_bets


def test_component_sign_orientation_is_deterministic_across_runs():
    data = _shared_factor_universe()
    weights = _equal_weights(data)

    reports = [compute_factor_concentration_report(data, weights) for _ in range(3)]

    assert reports[0].loadings == reports[1].loadings == reports[2].loadings
    # The dominant loading of each displayed factor is positive by convention.
    for factor_loadings in reports[0].loadings.values():
        dominant = max(factor_loadings.values(), key=abs)
        assert dominant > 0


def test_loadings_reconstruct_standardized_variance_when_all_factors_displayed():
    data = _independent_universe()
    report = compute_factor_concentration_report(
        data, _equal_weights(data), explained_variance_target=1.0
    )
    assert report.displayed_factor_count == len(data)
    assert max(report.residual_risk_by_position.values()) < 1e-5


def test_report_contains_no_trade_or_target_weight_field():
    data = _shared_factor_universe()
    payload = compute_factor_concentration_report(data, _equal_weights(data)).to_dict()

    forbidden = {
        "side", "shares", "quantity", "order_type", "limit_price", "stop_price",
        "approved", "execute", "authorization", "target_weight", "target_weights",
        "proposed_trades", "recommendation",
    }
    assert not (forbidden & set(payload)), forbidden & set(payload)
    assert payload["production_authoritative"] is False
    assert payload["evidence_status"] == "exploratory"


def test_both_doc_baselines_are_reported_alongside_the_pca():
    data = _shared_factor_universe()
    clusters = ["SEMI1+SEMI2+SEMI3 move together"]
    report = compute_factor_concentration_report(
        data, _equal_weights(data), correlation_clusters=clusters
    )

    # Baseline 1: the existing correlation-cluster output.
    assert report.correlation_clusters == tuple(clusters)
    # Baseline 2: Ledoit-Wolf shrinkage.
    assert report.shrinkage_baseline["estimator"] == "sklearn.covariance.LedoitWolf"
    assert 0.0 <= report.shrinkage_baseline["shrinkage_coefficient"] <= 1.0


def test_insufficient_observations_refuses():
    n = 40
    rng = np.random.default_rng(0)
    index = _index(n)
    data = {
        f"T{i}": _prices_from_returns(rng.normal(0, 0.02, n), index) for i in range(3)
    }

    report = compute_factor_concentration_report(
        data, _equal_weights(data), lookback_sessions=252, min_observations=60
    )

    assert not report.available
    assert "common observations" in report.unavailable_reason


def test_rejects_invalid_parameters():
    data = _independent_universe()
    weights = _equal_weights(data)
    with pytest.raises(FactorRiskError, match="min_observations"):
        compute_factor_concentration_report(data, weights, min_observations=5)
    with pytest.raises(FactorRiskError, match="lookback_sessions"):
        compute_factor_concentration_report(
            data, weights, lookback_sessions=30, min_observations=60
        )
    with pytest.raises(FactorRiskError, match="explained_variance_target"):
        compute_factor_concentration_report(data, weights, explained_variance_target=1.5)


def test_empty_input_is_unavailable_not_an_exception():
    report = compute_factor_concentration_report({}, {})
    assert not report.available
    assert report.unavailable_reason == "no price series supplied"


def test_report_is_json_serializable():
    import json

    data = _shared_factor_universe()
    json.dumps(compute_factor_concentration_report(data, _equal_weights(data)).to_dict())
