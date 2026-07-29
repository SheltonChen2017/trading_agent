"""
Sanity tests for assistant/risk_copilot.py. Run with:
python tests/test_assistant_risk_copilot.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import assistant.risk_copilot as risk_copilot
from assistant.context_builder import build_portfolio_snapshot
from assistant.policy import TradingPolicy
from assistant.risk_copilot import (
    check_concentration,
    check_policy_compliance,
    estimate_stress_impact,
    find_correlated_clusters,
)
from assistant.schemas import RiskExposure


def test_check_concentration_reports_specific_basket():
    risk = RiskExposure(
        basket_exposure_pct={"semiconductors": 55.0}, leveraged_etf_exposure_pct=0.0,
        cash_pct=10.0, largest_single_position_pct=30.0,
        concentration_warnings=["semiconductors exposure is 55.0% of total equity (via NVDA, AMD) — above the 40.0% concentration threshold."],
    )
    answer = check_concentration(risk, basket_name="semiconductors")
    assert "55.0%" in answer
    assert "flagged" in answer.lower()

    answer_unheld = check_concentration(risk, basket_name="utilities")
    assert "No current exposure" in answer_unheld


def test_check_concentration_general_summary_when_no_basket_given():
    clean_risk = RiskExposure(
        basket_exposure_pct={"tech": 20.0}, leveraged_etf_exposure_pct=0.0,
        cash_pct=50.0, largest_single_position_pct=15.0, concentration_warnings=[],
    )
    assert "No concentration warnings" in check_concentration(clean_risk)

    flagged_risk = RiskExposure(
        basket_exposure_pct={"tech": 80.0}, leveraged_etf_exposure_pct=0.0,
        cash_pct=5.0, largest_single_position_pct=50.0,
        concentration_warnings=["tech exposure is 80.0% -- above threshold."],
    )
    assert "Concentration warnings" in check_concentration(flagged_risk)


def test_find_correlated_clusters_flags_leveraged_plus_underlying():
    snapshot = build_portfolio_snapshot(
        [
            {"ticker": "QQQ", "shares": 10, "entry_price": 400.0, "current_price": 400.0},
            {"ticker": "TQQQ", "shares": 10, "entry_price": 50.0, "current_price": 50.0},
            {"ticker": "KO", "shares": 10, "entry_price": 60.0, "current_price": 60.0},
        ],
        cash=0.0,
    )
    warnings = find_correlated_clusters(snapshot)
    assert len(warnings) == 1
    assert "QQQ" in warnings[0] and "TQQQ" in warnings[0]


def test_find_correlated_clusters_silent_when_only_one_side_held():
    snapshot = build_portfolio_snapshot(
        [{"ticker": "QQQ", "shares": 10, "entry_price": 400.0, "current_price": 400.0}], cash=0.0,
    )
    assert find_correlated_clusters(snapshot) == []


def test_find_correlated_clusters_does_not_flag_an_inverse_etf_as_duplication():
    # GPT review, 2026-07-28: SPY + SPXU was reproduced being described as
    # "one amplified SPY bet" -- SPXU is INVERSE (moves opposite SPY), so
    # holding both is a partial hedge, not duplicated same-direction
    # exposure the way SPY + UPRO would be.
    snapshot = build_portfolio_snapshot(
        [
            {"ticker": "SPY", "shares": 10, "entry_price": 500.0, "current_price": 500.0},
            {"ticker": "SPXU", "shares": 10, "entry_price": 10.0, "current_price": 10.0},
        ],
        cash=0.0,
    )
    assert find_correlated_clusters(snapshot) == []


def test_find_correlated_clusters_still_flags_a_non_inverse_leveraged_pair():
    # Regression guard: the inverse-ETF exclusion must not silently
    # disable the warning for genuine same-direction duplication.
    snapshot = build_portfolio_snapshot(
        [
            {"ticker": "SPY", "shares": 10, "entry_price": 500.0, "current_price": 500.0},
            {"ticker": "UPRO", "shares": 10, "entry_price": 80.0, "current_price": 80.0},
        ],
        cash=0.0,
    )
    warnings = find_correlated_clusters(snapshot)
    assert len(warnings) == 1
    assert "SPY" in warnings[0] and "UPRO" in warnings[0]


# --- check_policy_compliance() (GPT review, 2026-07-28): check_concentration()
# uses fixed informational thresholds unrelated to the active policy -- a
# 10% position with a 5% policy max_position_pct reported "no concentration
# warnings" while proposal generation would actually flag it. This function
# checks the SAME numeric caps generate_risk_reduction_proposals() uses.
#
# Follow-up GPT review, 2026-07-28: the first version of this function used
# RiskExposure.basket_exposure_pct (rounded to 1 decimal for display by
# build_risk_exposure()) instead of exact values, and didn't check
# max_total_exposure_pct or min_cash_reserve_pct at all. Fixed to compute
# every percentage directly from PortfolioSnapshot and cover all 5 policy
# limits; check_policy_compliance() no longer takes a `risk` argument.

def _policy(
    max_position_pct=0.05, max_basket_pct=0.40, max_leveraged_etf_pct=0.20,
    max_total_exposure_pct=0.50, min_cash_reserve_pct=0.0,
):
    return TradingPolicy(
        version="test", name="test", execution_mode="paper",
        max_position_pct=max_position_pct, max_total_exposure_pct=max_total_exposure_pct,
        max_basket_pct=max_basket_pct, max_leveraged_etf_pct=max_leveraged_etf_pct,
        min_cash_reserve_pct=min_cash_reserve_pct,
    )


def test_check_policy_compliance_flags_a_position_over_the_policy_cap():
    positions = [{"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 100.0}]
    snapshot = build_portfolio_snapshot(positions, cash=9_000.0)  # AAPL = 1000/10000 = 10%
    violations = check_policy_compliance(snapshot, _policy(max_position_pct=0.05))
    assert any("AAPL" in v and "10.00%" in v for v in violations)


def test_check_policy_compliance_silent_when_within_the_policy_cap():
    positions = [{"ticker": "AAPL", "shares": 1, "entry_price": 100.0, "current_price": 100.0}]
    snapshot = build_portfolio_snapshot(positions, cash=9_900.0)  # AAPL = 100/10000 = 1%
    assert check_policy_compliance(snapshot, _policy(max_position_pct=0.05)) == []


def test_check_policy_compliance_flags_a_basket_breach_rounding_would_have_hidden():
    # GPT review, 2026-07-28, reproduced: exact basket exposure of 40.04%
    # against a 40% policy limit rounded to 40.0% via
    # RiskExposure.basket_exposure_pct and silently evaded the old version
    # of this check. AAPL is a member of config.BASKETS["tech"].
    positions = [{"ticker": "AAPL", "shares": 1, "entry_price": 4_004.0, "current_price": 4_004.0}]
    snapshot = build_portfolio_snapshot(positions, cash=5_996.0)  # AAPL = 4004/10000 = 40.04%
    violations = check_policy_compliance(snapshot, _policy(max_position_pct=1.0, max_basket_pct=0.40))
    assert any("tech" in v and "40.04%" in v for v in violations)


def test_check_policy_compliance_flags_total_exposure_over_the_cap():
    # GPT review, 2026-07-28, reproduced: a 60%-invested portfolio against
    # a 50% max_total_exposure_pct limit reported no violation at all --
    # this check was entirely missing.
    positions = [{"ticker": "AAPL", "shares": 1, "entry_price": 6_000.0, "current_price": 6_000.0}]
    snapshot = build_portfolio_snapshot(positions, cash=4_000.0)  # invested = 6000/10000 = 60%
    violations = check_policy_compliance(
        snapshot, _policy(max_position_pct=1.0, max_basket_pct=1.0, max_leveraged_etf_pct=1.0, max_total_exposure_pct=0.50),
    )
    assert any("Total invested exposure" in v and "60.00%" in v for v in violations)


def test_check_policy_compliance_flags_cash_reserve_below_the_minimum():
    positions = [{"ticker": "AAPL", "shares": 1, "entry_price": 9_500.0, "current_price": 9_500.0}]
    snapshot = build_portfolio_snapshot(positions, cash=500.0)  # cash = 500/10000 = 5%
    violations = check_policy_compliance(
        snapshot,
        _policy(
            max_position_pct=1.0, max_basket_pct=1.0, max_leveraged_etf_pct=1.0,
            max_total_exposure_pct=1.0, min_cash_reserve_pct=0.10,
        ),
    )
    assert any("Cash reserve" in v and "5.00%" in v for v in violations)


def _synthetic_price_series(returns: np.ndarray, start_price: float = 100.0) -> pd.DataFrame:
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=len(returns))
    close = start_price * np.cumprod(1 + returns)
    return pd.DataFrame(
        {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": 1_000_000.0},
        index=dates,
    )


def test_estimate_stress_impact_computes_beta_from_real_relationship():
    # Ticker "DOUBLE" moves exactly 2x the benchmark, "HALF" moves 0.5x --
    # a real, known linear relationship the beta calc should recover.
    rng = np.random.default_rng(0)
    benchmark_returns = rng.normal(0, 0.01, size=260)
    double_returns = 2.0 * benchmark_returns
    half_returns = 0.5 * benchmark_returns

    original_fetch = risk_copilot.fetch_historical
    try:
        risk_copilot.fetch_historical = lambda tickers, lookback_days=252: {
            "BENCH": _synthetic_price_series(benchmark_returns),
            "DOUBLE": _synthetic_price_series(double_returns),
            "HALF": _synthetic_price_series(half_returns),
        }
        snapshot = build_portfolio_snapshot(
            [
                {"ticker": "DOUBLE", "shares": 10, "entry_price": 100.0, "current_price": 100.0},
                {"ticker": "HALF", "shares": 10, "entry_price": 100.0, "current_price": 100.0},
            ],
            cash=0.0,
        )
        result = estimate_stress_impact(snapshot, "BENCH", benchmark_move_pct=-5.0)

        double_impact = next(p for p in result["position_impacts"] if p["ticker"] == "DOUBLE")
        half_impact = next(p for p in result["position_impacts"] if p["ticker"] == "HALF")
        assert abs(double_impact["beta"] - 2.0) < 0.05
        assert abs(half_impact["beta"] - 0.5) < 0.05
        # -5% benchmark move * beta 2.0 * $1000 position = -$100
        assert abs(double_impact["estimated_impact"] - (-100.0)) < 5.0
        assert "warning" not in result
    finally:
        risk_copilot.fetch_historical = original_fetch


def test_estimate_stress_impact_flags_missing_beta_without_dropping_silently():
    original_fetch = risk_copilot.fetch_historical
    try:
        risk_copilot.fetch_historical = lambda tickers, lookback_days=252: {
            "BENCH": _synthetic_price_series(np.random.default_rng(1).normal(0, 0.01, size=260)),
            # "NODATA" ticker deliberately absent
        }
        snapshot = build_portfolio_snapshot(
            [{"ticker": "NODATA", "shares": 10, "entry_price": 100.0, "current_price": 100.0}], cash=0.0,
        )
        result = estimate_stress_impact(snapshot, "BENCH", benchmark_move_pct=-5.0)
        assert result["position_impacts"][0]["beta"] is None
        assert "warning" in result
        assert "NODATA" in result["warning"]
    finally:
        risk_copilot.fetch_historical = original_fetch


if __name__ == "__main__":
    test_check_concentration_reports_specific_basket()
    test_check_concentration_general_summary_when_no_basket_given()
    test_find_correlated_clusters_flags_leveraged_plus_underlying()
    test_find_correlated_clusters_silent_when_only_one_side_held()
    test_find_correlated_clusters_does_not_flag_an_inverse_etf_as_duplication()
    test_find_correlated_clusters_still_flags_a_non_inverse_leveraged_pair()
    test_check_policy_compliance_flags_a_position_over_the_policy_cap()
    test_check_policy_compliance_silent_when_within_the_policy_cap()
    test_check_policy_compliance_flags_a_basket_breach_rounding_would_have_hidden()
    test_check_policy_compliance_flags_total_exposure_over_the_cap()
    test_check_policy_compliance_flags_cash_reserve_below_the_minimum()
    test_estimate_stress_impact_computes_beta_from_real_relationship()
    test_estimate_stress_impact_flags_missing_beta_without_dropping_silently()
    print("All assistant risk copilot tests passed.")
