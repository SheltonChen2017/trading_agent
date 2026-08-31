"""Regression coverage for explicit risk-exposure availability evidence."""

import math
from decimal import localcontext

import pytest

from assistant.context_builder import build_portfolio_snapshot, build_risk_exposure
from assistant.llm.projection import (
    ProjectionError,
    _finite_number,
    project_committee_input,
)
from assistant.llm.schemas import FactAvailability, PrivacyMode
from assistant.risk_copilot import check_concentration
from assistant.schemas import (
    DecisionPacket,
    MarketRegime,
    PortfolioPosition,
    PortfolioSnapshot,
    RiskExposure,
)


def test_integrity_failure_is_unavailable_and_never_rendered_as_all_clear():
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
        as_of="2026-08-27",
    )

    exposure = build_risk_exposure(malformed)
    summary = check_concentration(exposure)

    assert exposure.available is False
    assert exposure.unavailable_reason
    assert "unavailable" in summary.lower()
    assert "no concentration warnings" not in summary.lower()


def test_exposure_threshold_uses_exact_value_before_display_rounding():
    snapshot = build_portfolio_snapshot(
        [
            {
                "ticker": "AAPL",
                "shares": "1",
                "entry_price": "40.04",
                "current_price": "40.04",
            }
        ],
        cash="59.96",
    )

    exposure = build_risk_exposure(snapshot, concentration_threshold_pct=40.0)

    assert exposure.available is True
    assert exposure.basket_exposure_pct["tech"] == 40.0
    assert any(
        "tech exposure is 40.0%" in warning
        for warning in exposure.concentration_warnings
    )


def test_exposure_threshold_ignores_lowered_ambient_decimal_precision():
    snapshot = build_portfolio_snapshot(
        [
            {
                "ticker": "AAPL",
                "shares": "1",
                "entry_price": "40.04",
                "current_price": "40.04",
            }
        ],
        cash="59.96",
    )

    with localcontext() as context:
        context.prec = 2
        exposure = build_risk_exposure(
            snapshot,
            concentration_threshold_pct=40.0,
        )

    assert exposure.available is True
    assert exposure.basket_exposure_pct["tech"] == 40.0
    assert any(
        "tech exposure is 40.0%" in warning
        for warning in exposure.concentration_warnings
    )


@pytest.mark.parametrize(
    "threshold",
    (
        float("nan"),
        float("inf"),
        float("-inf"),
        True,
        "not-a-number",
        -0.1,
        100.1,
    ),
)
def test_exposure_threshold_rejects_non_finite_or_non_numeric_values(threshold):
    snapshot = build_portfolio_snapshot(
        [{"ticker": "AAPL", "shares": "1", "entry_price": "10", "current_price": "10"}],
        cash="90",
    )

    with pytest.raises(ValueError, match="concentration_threshold_pct"):
        build_risk_exposure(snapshot, concentration_threshold_pct=threshold)


def test_projection_normalizes_a_huge_integer_to_projection_error():
    with pytest.raises(ProjectionError, match="must be finite"):
        _finite_number(10**10000, name="candidate.test")


@pytest.mark.parametrize("total_equity_exact", ("0.001", "1e-309"))
def test_impossible_exact_percentage_marks_exposure_unavailable(
    total_equity_exact,
):
    # The canonical snapshot contract permits an absolute component-equity
    # difference of one cent. At a tiny exact total, that bounded dollar
    # tolerance can imply either a huge finite percentage or one too large for
    # a display float. Neither may be published as an available exposure.
    position = PortfolioPosition(
        ticker="AAPL",
        shares=1.0,
        entry_price=0.005,
        current_price=0.005,
        market_value=0.0,
        unrealized_pnl_pct=0.0,
        is_leveraged_etf=False,
        shares_exact="1",
        entry_price_exact="0.005",
        current_price_exact="0.005",
        market_value_exact="0.005",
    )
    snapshot = PortfolioSnapshot(
        positions=[position],
        cash=0.0,
        total_equity=0.0,
        as_of="2026-08-27",
        cash_exact="0",
        total_equity_exact=total_equity_exact,
    )

    exposure = build_risk_exposure(snapshot)

    assert exposure.available is False
    assert exposure.unavailable_reason
    assert all(math.isfinite(value) for value in exposure.basket_exposure_pct.values())
    assert math.isfinite(exposure.largest_single_position_pct)


def test_llm_projection_exposes_unavailability_not_zero_risk_metrics():
    portfolio = build_portfolio_snapshot(
        [
            {
                "ticker": "NVDA",
                "shares": "10",
                "entry_price": "100",
                "current_price": "200",
            }
        ],
        cash="2000",
    )
    packet = DecisionPacket(
        generated_at="2026-08-27T12:00:00+00:00",
        portfolio=portfolio,
        risk=RiskExposure(
            basket_exposure_pct={},
            leveraged_etf_exposure_pct=0.0,
            cash_pct=0.0,
            largest_single_position_pct=0.0,
            concentration_warnings=["Portfolio integrity unavailable"],
            available=False,
            unavailable_reason="Portfolio integrity unavailable",
        ),
        regime=MarketRegime(
            benchmark_ticker="QQQ",
            trend="uptrend",
            volatility_regime="low_vol",
            trailing_volatility_pct=18.0,
            as_of="2026-08-27",
        ),
        signals=[],
        upcoming_events=[],
        warnings=[],
        policy_version="paper-v1",
        analytics={
            "available": False,
            "unavailable_reason": "Portfolio integrity unavailable",
            "invested_pct": 50.0,
            "unrealized_pnl_pct": 100.0,
            "position_weights_pct": {"NVDA": 50.0},
        },
        data_freshness={"portfolio_as_of": portfolio.as_of},
    )
    proposal = {
        "proposal_id": "tp_unavailable",
        "created_at": "2026-08-27T12:00:00+00:00",
        "evidence_status": "deterministic_risk_policy",
        "intent": {
            "ticker": "NVDA",
            "side": "sell",
            "shares": 5,
            "order_type": "market",
            "rationale": "risk reduction",
        },
        "reference_price": 200.0,
        "expected_impact": {
            "trade_value": 1000.0,
            "position_weight_before_pct": 50.0,
            "position_weight_after_pct": 25.0,
            "cash_before": 2000.0,
            "cash_after": 3000.0,
            "invested_pct_after": 25.0,
        },
    }

    projected = project_committee_input(packet, proposal)

    assert "metric.cash_pct" not in projected.fact_by_id
    assert "metric.largest_position_pct" not in projected.fact_by_id
    assert "metric.leveraged_etf_exposure_pct" not in projected.fact_by_id
    assert "metric.invested_pct" not in projected.fact_by_id
    assert "metric.unrealized_pnl_pct" not in projected.fact_by_id
    assert "holding.nvda.weight_pct" not in projected.fact_by_id
    availability = projected.fact_by_id["risk.exposure_availability"]
    assert availability.availability == FactAvailability.UNAVAILABLE
    assert availability.critical is True
    for source_id in (
        "candidate.position_weight_before_pct",
        "candidate.position_weight_after_pct",
    ):
        fact = projected.fact_by_id[source_id]
        assert fact.value == "unavailable"
        assert fact.availability == FactAvailability.UNAVAILABLE
        assert fact.production_authoritative is False
        assert fact.critical is True
    assert "candidate.invested_pct_after" not in projected.fact_by_id
    assert projected.fact_by_id["candidate.side"].production_authoritative is True

    exact_dollars = project_committee_input(
        packet,
        proposal,
        privacy_mode=PrivacyMode.EXACT_DOLLARS,
    )
    assert not any(
        source_id.startswith("value.")
        for source_id in exact_dollars.fact_by_id
    )
    for source_id in (
        "candidate.trade_value",
        "candidate.cash_before",
        "candidate.cash_after",
    ):
        fact = exact_dollars.fact_by_id[source_id]
        assert fact.value == "unavailable"
        assert fact.availability == FactAvailability.UNAVAILABLE
        assert fact.production_authoritative is False
