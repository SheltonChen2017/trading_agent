"""
Sanity tests for assistant/risk_copilot.py. Run with:
python tests/test_assistant_risk_copilot.py
"""
import sys
from decimal import localcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import pytest

import assistant.risk_copilot as risk_copilot
from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.policy import TradingPolicy
from assistant.risk_copilot import (
    check_concentration,
    check_policy_compliance,
    estimate_stress_impact,
    find_correlated_clusters,
    portfolio_risk_decomposition,
)
from assistant.portfolio_snapshot import PortfolioSnapshotIntegrityError
from assistant.schemas import PortfolioPosition, PortfolioSnapshot, RiskExposure
from risk.execution_gate import TradeIntent, ViolationCode, validate_trade_intent


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


@pytest.mark.parametrize(
    "positions,cash,buying_power",
    [
        ([{"ticker": "AAPL", "shares": -1, "entry_price": 10, "current_price": 10}], 100, None),
        ([{"ticker": "AAPL", "shares": 0, "entry_price": 10, "current_price": 10, "market_value": 1}], 100, None),
        ([{"ticker": "AAPL", "shares": 1, "entry_price": 0, "current_price": 10}], 100, None),
        ([{"ticker": "AAPL", "shares": 1, "entry_price": 10, "current_price": 0}], 100, None),
        ([{"ticker": "AAPL", "shares": 1, "entry_price": 10, "current_price": 10, "market_value": 11}], 100, None),
        ([], -1, None),
        ([], 100, -1),
    ],
)
def test_snapshot_builder_refuses_non_long_only_or_inconsistent_state(
    positions, cash, buying_power
):
    with pytest.raises(PortfolioSnapshotIntegrityError):
        build_portfolio_snapshot(
            positions,
            cash=cash,
            buying_power=buying_power,
        )


def test_zero_share_zero_value_row_is_normalized_to_not_held_state():
    snapshot = build_portfolio_snapshot(
        [
            {
                "ticker": "AAPL",
                "shares": 0,
                "entry_price": 10,
                "current_price": 10,
            }
        ],
        cash=100,
    )

    assert snapshot.positions == []
    assert snapshot.total_equity_exact == "100"


def test_snapshot_builder_aggregates_exact_values_before_display_rounding():
    snapshot = build_portfolio_snapshot(
        [
            {
                "ticker": "KO-A",
                "shares": "1",
                "entry_price": "24.997",
                "current_price": "24.997",
            },
            {
                "ticker": "KO",
                "shares": "1",
                "entry_price": "24.997",
                "current_price": "24.997",
            },
        ],
        cash="50.006",
    )

    assert [position.market_value for position in snapshot.positions] == [25.0, 25.0]
    assert snapshot.total_equity_exact == "100"
    assert snapshot.total_equity == 100.0


def test_direct_malformed_snapshot_is_degraded_in_reports_and_blocked_by_gate():
    malformed = PortfolioSnapshot(
        positions=[
            PortfolioPosition(
                ticker="AAPL",
                shares=-1,
                entry_price=10,
                current_price=10,
                market_value=-10,
                unrealized_pnl_pct=0,
                is_leveraged_etf=False,
            )
        ],
        cash=110,
        total_equity=100,
        as_of="2026-08-26",
    )
    policy = TradingPolicy(version="integrity-test", name="integrity-test")

    compliance = check_policy_compliance(malformed, policy)
    exposure = build_risk_exposure(malformed)
    gate = validate_trade_intent(
        TradeIntent(ticker="AAPL", side="sell", shares=1),
        malformed,
        reference_price=10,
    )

    assert compliance and "integrity unavailable" in compliance[0].lower()
    assert exposure.concentration_warnings
    assert "integrity unavailable" in exposure.concentration_warnings[0].lower()
    assert ViolationCode.INVALID_POSITION_DATA.value in gate.violation_codes


def test_coherent_extreme_exact_evidence_remains_available():
    extreme = PortfolioSnapshot(
        positions=[],
        cash=1e308,
        total_equity=1e308,
        cash_exact="1e308",
        total_equity_exact="1e308",
        as_of="2026-08-27",
    )
    policy = TradingPolicy(version="integrity-test", name="integrity-test")

    compliance = check_policy_compliance(extreme, policy)
    exposure = build_risk_exposure(extreme)
    gate = validate_trade_intent(
        TradeIntent(ticker="AAPL", side="sell", shares=1),
        extreme,
        reference_price=10,
    )

    assert compliance == []
    assert exposure.available is True
    assert exposure.cash_pct == 100.0
    assert ViolationCode.INVALID_POSITION_DATA.value not in gate.violation_codes
    assert ViolationCode.SELL_EXCEEDS_HELD.value in gate.violation_codes


def test_policy_compliance_boundary_ignores_lowered_decimal_precision():
    snapshot = build_portfolio_snapshot(
        [
            {
                "ticker": "AAPL",
                "shares": "1",
                "entry_price": "5.004",
                "current_price": "5.004",
            }
        ],
        cash="94.996",
    )
    policy = TradingPolicy(
        version="precision-test",
        name="precision-test",
        max_position_pct=0.05,
        max_total_exposure_pct=0.05,
        max_basket_pct=0.05,
        max_leveraged_etf_pct=1.0,
        min_cash_reserve_pct=0.95,
    )

    with localcontext() as context:
        context.prec = 2
        violations = check_policy_compliance(snapshot, policy)

    assert any("AAPL is 5.00%" in violation for violation in violations)
    assert any("Basket 'tech' is 5.00%" in violation for violation in violations)
    assert any("Total invested exposure is 5.00%" in violation for violation in violations)
    assert any("Cash reserve is 95.00%" in violation for violation in violations)


def test_execution_gate_uses_canonical_duplicate_ticker_integrity_contract():
    duplicate = PortfolioSnapshot(
        positions=[
            PortfolioPosition(
                ticker="AAPL",
                shares=1,
                entry_price=10,
                current_price=10,
                market_value=10,
                unrealized_pnl_pct=0,
                is_leveraged_etf=False,
            ),
            PortfolioPosition(
                ticker="AAPL",
                shares=1,
                entry_price=10,
                current_price=10,
                market_value=10,
                unrealized_pnl_pct=0,
                is_leveraged_etf=False,
            ),
        ],
        cash=100,
        total_equity=120,
        as_of="2026-08-27",
    )

    gate = validate_trade_intent(
        TradeIntent(ticker="AAPL", side="sell", shares=1),
        duplicate,
        reference_price=10,
    )

    assert gate.approved is False
    assert ViolationCode.INVALID_POSITION_DATA.value in gate.violation_codes
    assert any("duplicate position row" in item for item in gate.violations)


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
    violations = check_policy_compliance(
        snapshot,
        _policy(max_position_pct=0.50, max_basket_pct=0.40),
    )
    assert any("tech" in v and "40.04%" in v for v in violations)


def test_check_policy_compliance_flags_lowercase_ticker_basket_exposure():
    # Independent review reproduction: a manually-supplied lowercase
    # "aapl" position used to be invisible to check_policy_compliance()'s
    # case-sensitive basket membership check even though it's 50% exposed
    # to the "tech" basket via AAPL.
    positions = [{"ticker": "aapl", "shares": 50, "entry_price": 100.0, "current_price": 100.0}]
    snapshot = build_portfolio_snapshot(positions, cash=5_000.0)  # AAPL = 5000/10000 = 50%
    violations = check_policy_compliance(
        snapshot, _policy(max_position_pct=1.0, max_basket_pct=0.40, max_leveraged_etf_pct=1.0, max_total_exposure_pct=1.0),
    )
    assert any("tech" in v and "50.00%" in v for v in violations)


def test_check_policy_compliance_aggregates_duplicate_ticker_rows_against_position_cap():
    # Independent review reproduction: two AAPL lots of $300 each used to
    # remain two separate rows (3% each), each individually under a 5%
    # max_position_pct cap even though their combined 6% exposure exceeds
    # it. build_portfolio_snapshot() now aggregates duplicate rows at
    # ingestion, so check_policy_compliance() sees one $600 position.
    positions = [
        {"ticker": "AAPL", "shares": 1, "entry_price": 300.0, "current_price": 300.0},
        {"ticker": "AAPL", "shares": 1, "entry_price": 300.0, "current_price": 300.0},
    ]
    snapshot = build_portfolio_snapshot(positions, cash=9_400.0)  # total = 10000, AAPL = 600/10000 = 6%
    assert len(snapshot.positions) == 1
    violations = check_policy_compliance(
        snapshot, _policy(max_position_pct=0.05, max_basket_pct=1.0, max_leveraged_etf_pct=1.0, max_total_exposure_pct=1.0),
    )
    assert any("AAPL" in v and "6.00%" in v for v in violations)


def test_check_policy_compliance_flags_total_exposure_over_the_cap():
    # GPT review, 2026-07-28, reproduced: a 60%-invested portfolio against
    # a 50% max_total_exposure_pct limit reported no violation at all --
    # this check was entirely missing.
    positions = [
        {
            "ticker": "AAA",
            "shares": 1,
            "entry_price": 3_000.0,
            "current_price": 3_000.0,
        },
        {
            "ticker": "BBB",
            "shares": 1,
            "entry_price": 3_000.0,
            "current_price": 3_000.0,
        },
    ]
    snapshot = build_portfolio_snapshot(
        positions, cash=4_000.0
    )  # invested = 6000/10000 = 60%; each position = 30%
    violations = check_policy_compliance(
        snapshot,
        _policy(
            max_position_pct=0.50,
            max_basket_pct=1.0,
            max_leveraged_etf_pct=1.0,
            max_total_exposure_pct=0.50,
        ),
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


def test_portfolio_risk_decomposition_finds_empirical_cluster_and_beta():
    rng = np.random.default_rng(42)
    market = rng.normal(0, 0.01, size=260)
    shared = rng.normal(0, 0.002, size=260)
    aaa = 1.2 * market + shared
    bbb = 1.1 * market + shared * 0.8
    ccc = rng.normal(0, 0.012, size=260)
    data = {
        "SPY": _synthetic_price_series(market),
        "AAA": _synthetic_price_series(aaa),
        # Explicitly shorter history: alignment must use the shared dates.
        "BBB": _synthetic_price_series(bbb).iloc[10:],
        "CCC": _synthetic_price_series(ccc),
    }
    # One corrupt provider value must be dropped jointly, not create a NaN
    # correlation that silently looks like "no concentration."
    data["AAA"].iloc[50, data["AAA"].columns.get_loc("close")] = np.nan
    original_fetch = risk_copilot.fetch_historical
    try:
        risk_copilot.fetch_historical = (
            lambda tickers, lookback_days=252: data
        )
        snapshot = build_portfolio_snapshot(
            [
                {
                    "ticker": ticker,
                    "shares": 10,
                    "entry_price": 100.0,
                    "current_price": 100.0,
                }
                for ticker in ("AAA", "BBB", "CCC")
            ],
            cash=1_000.0,
        )
        result = portfolio_risk_decomposition(
            snapshot, min_observations=100, correlation_threshold=0.75
        )
    finally:
        risk_copilot.fetch_historical = original_fetch

    assert result["available"], result
    assert result["common_observations"] >= 100
    assert result["portfolio_beta"] is not None
    assert np.isfinite(result["annualized_volatility_pct"])
    assert abs(
        sum(
            row["contribution_to_variance_pct"]
            for row in result["contributions"]
        )
        - 100
    ) < 0.01
    assert any(
        {"AAA", "BBB"}.issubset(set(cluster["tickers"]))
        for cluster in result["correlated_clusters"]
    )


def test_portfolio_risk_decomposition_fails_closed_without_common_dates():
    rng = np.random.default_rng(5)
    first = _synthetic_price_series(rng.normal(0, 0.01, size=100))
    second = _synthetic_price_series(rng.normal(0, 0.01, size=100))
    second.index = second.index + pd.Timedelta(days=500)
    benchmark = _synthetic_price_series(rng.normal(0, 0.01, size=100))
    original_fetch = risk_copilot.fetch_historical
    try:
        risk_copilot.fetch_historical = (
            lambda tickers, lookback_days=252: {
                "AAA": first,
                "BBB": second,
                "SPY": benchmark,
            }
        )
        snapshot = build_portfolio_snapshot(
            [
                {
                    "ticker": ticker,
                    "shares": 1,
                    "entry_price": 100.0,
                    "current_price": 100.0,
                }
                for ticker in ("AAA", "BBB")
            ],
            cash=0,
        )
        result = portfolio_risk_decomposition(
            snapshot, min_observations=60
        )
    finally:
        risk_copilot.fetch_historical = original_fetch

    assert not result["available"]
    assert "common finite observations" in result["reason"]


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
    test_check_policy_compliance_flags_lowercase_ticker_basket_exposure()
    test_check_policy_compliance_aggregates_duplicate_ticker_rows_against_position_cap()
    test_check_policy_compliance_flags_total_exposure_over_the_cap()
    test_check_policy_compliance_flags_cash_reserve_below_the_minimum()
    test_estimate_stress_impact_computes_beta_from_real_relationship()
    test_estimate_stress_impact_flags_missing_beta_without_dropping_silently()
    print("All assistant risk copilot tests passed.")
