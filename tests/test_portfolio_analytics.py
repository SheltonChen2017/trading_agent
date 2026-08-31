"""Tests for assistant/portfolio_analytics.py."""
import sys
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.context_builder import build_portfolio_snapshot
from assistant.portfolio_analytics import (
    compute_portfolio_analytics,
    estimate_pending_buy_value_by_ticker,
    preview_trade_impact,
)
from assistant.portfolio_snapshot import PortfolioSnapshotIntegrityError
from assistant.schemas import PortfolioPosition, PortfolioSnapshot


def test_preview_trade_impact_folds_in_same_ticker_pending_buy_orders():
    # Independent review, 2026-07-31: preview_trade_impact() used to compute
    # existing_value purely from snapshot.positions, ignoring pending
    # (not-yet-filled) buy orders for the SAME ticker -- unlike
    # risk/execution_gate.py, which folds pending_buy_value_by_ticker into
    # every exposure check for exactly this reason. Trigger: approve one
    # leg of a multi-ticker purchase (now a pending order), then preview a
    # second proposal for the SAME ticker -- the preview must reflect the
    # already-reserved notional, not just currently-held shares.
    snapshot = build_portfolio_snapshot(
        [{"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 100.0}],
        cash=8_000.0,
        open_orders=[
            {"ticker": "AAPL", "side": "buy", "shares": 5, "limit_price": 100.0},
        ],
    )
    # total_equity = 8_000 cash + 1_000 held = 9_000
    impact = preview_trade_impact(snapshot, "AAPL", "buy", shares=2, reference_price=100.0)

    # held (1_000) + pending (500) = 1_500 -> 1_500 / 9_000 = 16.67%
    assert impact["position_weight_before_pct"] == 16.67
    # + this new 200 trade -> 1_700 / 9_000 = 18.89%
    assert impact["position_weight_after_pct"] == 18.89
    assert impact["pending_buy_value"] == 500.0
    assert impact["invested_pct_after"] == 18.89
    assert impact["cash_after"] == 7_300.0
    assert impact["projection_complete"] is True


def test_preview_trade_impact_ignores_pending_orders_for_other_tickers():
    snapshot = build_portfolio_snapshot(
        [{"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 100.0}],
        cash=8_000.0,
        open_orders=[
            {"ticker": "MSFT", "side": "buy", "shares": 5, "limit_price": 100.0},
        ],
    )
    impact = preview_trade_impact(snapshot, "AAPL", "buy", shares=2, reference_price=100.0)
    assert impact["pending_buy_value"] == 0.0
    assert impact["position_weight_before_pct"] == round(1_000 / 9_000 * 100, 2)


def test_preview_trade_impact_ignores_pending_sell_orders():
    snapshot = build_portfolio_snapshot(
        [{"ticker": "AAPL", "shares": 10, "entry_price": 100.0, "current_price": 100.0}],
        cash=8_000.0,
        open_orders=[
            {"ticker": "AAPL", "side": "sell", "shares": 5, "limit_price": 100.0},
        ],
    )
    impact = preview_trade_impact(snapshot, "AAPL", "buy", shares=2, reference_price=100.0)
    assert impact["pending_buy_value"] == 0.0


def test_preview_marks_plain_market_pending_buy_as_incomplete():
    snapshot = build_portfolio_snapshot(
        [
            {
                "ticker": "AAPL",
                "shares": 10,
                "entry_price": 100.0,
                "current_price": 100.0,
            }
        ],
        cash=8_000.0,
        open_orders=[
            {"ticker": "AAPL", "side": "buy", "shares": 5},
        ],
    )

    impact = preview_trade_impact(
        snapshot, "AAPL", "buy", shares=2, reference_price=100.0
    )

    assert impact["projection_complete"] is False
    assert impact["pending_buy_unknown_tickers"] == ["AAPL"]


def test_preview_trade_impact_invested_value_matches_compute_portfolio_analytics():
    # Independent review, 2026-07-31 (P2 #3): preview_trade_impact() and
    # compute_portfolio_analytics() used to compute "current invested
    # value" via two different formulas -- total_equity - cash vs. a direct
    # sum of position.market_value. Mathematically equal by the snapshot's
    # own construction invariant, but two independently-rounded float paths
    # with no enforced agreement (independent review: values chosen so the
    # two formulas' raw floats actually differ by float epsilon, e.g.
    # 2111.11 vs 2111.1099999999997). Now both use the same direct-sum
    # formula, so a no-op preview (0 shares) must agree exactly with the
    # ordinary briefing's invested percentage.
    snapshot = build_portfolio_snapshot(
        [
            {"ticker": "AAPL", "shares": 1, "entry_price": 1111.11, "current_price": 1111.11},
            {"ticker": "MSFT", "shares": 1, "entry_price": 1000.0, "current_price": 1000.0},
        ],
        cash=1234.56,
    )
    analytics = compute_portfolio_analytics(snapshot)
    impact = preview_trade_impact(snapshot, "AAPL", "buy", shares=0, reference_price=1111.11)
    assert impact["invested_pct_after"] == analytics["invested_pct"]


def test_open_order_count_is_unavailable_when_the_book_was_not_observed():
    snapshot = build_portfolio_snapshot(
        [],
        cash=10_000.0,
        open_orders=[],
        open_orders_available=False,
    )

    assert compute_portfolio_analytics(snapshot)["open_order_count"] is None


def test_valid_analytics_payload_has_explicit_availability():
    snapshot = build_portfolio_snapshot([], cash="100")

    analytics = compute_portfolio_analytics(snapshot)

    assert analytics["available"] is True
    assert analytics["unavailable_reason"] is None


def test_buy_preview_refuses_unavailable_order_book_but_sell_remains_previewable():
    snapshot = build_portfolio_snapshot(
        [
            {
                "ticker": "AAPL",
                "shares": "2",
                "entry_price": "100",
                "current_price": "100",
            }
        ],
        cash="800",
        open_orders=[],
        open_orders_available=False,
    )

    with pytest.raises(ValueError, match="active-order data is unavailable"):
        preview_trade_impact(
            snapshot,
            "AAPL",
            "buy",
            shares=1,
            reference_price=100,
        )

    sell = preview_trade_impact(
        snapshot,
        "AAPL",
        "sell",
        shares=1,
        reference_price=100,
    )
    assert sell["position_weight_after_pct"] == 10.0
    assert sell["cash_after"] == 900.0
    assert sell["open_orders_available"] is False
    assert sell["projection_complete"] is False


def test_analytics_aggregates_exact_subcent_positions_before_display_rounding():
    snapshot = build_portfolio_snapshot(
        [
            {
                "ticker": ticker,
                "shares": "1",
                "entry_price": "0.003",
                "current_price": "0.004",
            }
            for ticker in ("AAA", "BBB", "CCC")
        ],
        cash="1",
    )

    analytics = compute_portfolio_analytics(snapshot)

    # Each legacy display market_value is $0.00; aggregate exact evidence is
    # $0.012 and must be rounded only after summation.
    assert [position.market_value for position in snapshot.positions] == [
        0.0,
        0.0,
        0.0,
    ]
    assert analytics["invested_value"] == 0.01
    assert analytics["invested_pct"] == 1.19
    assert analytics["position_weights_pct"] == {
        "AAA": 0.4,
        "BBB": 0.4,
        "CCC": 0.4,
    }


def test_analytics_and_preview_ignore_low_ambient_decimal_precision():
    snapshot = build_portfolio_snapshot(
        [
            {
                "ticker": "AAA",
                "shares": "3.000000001",
                "entry_price": "7.89",
                "current_price": "8.01",
            },
            {
                "ticker": "BBB",
                "shares": "2.000000001",
                "entry_price": "5.43",
                "current_price": "5.67",
            },
        ],
        cash="1234.56789",
        open_orders=[
            {
                "ticker": "AAA",
                "side": "buy",
                "shares": "1.25",
                "limit_price": "8.01",
            }
        ],
    )
    expected_analytics = compute_portfolio_analytics(snapshot)
    expected_preview = preview_trade_impact(
        snapshot,
        "AAA",
        "buy",
        shares="0.125",
        reference_price=Decimal("8.01"),
    )

    with localcontext() as context:
        context.prec = 2
        actual_analytics = compute_portfolio_analytics(snapshot)
        actual_preview = preview_trade_impact(
            snapshot,
            "AAA",
            "buy",
            shares="0.125",
            reference_price=Decimal("8.01"),
        )

    assert actual_analytics == expected_analytics
    assert actual_preview == expected_preview


def test_analytics_normalizes_unrepresentable_cost_basis_to_integrity_error():
    snapshot = build_portfolio_snapshot(
        [
            {
                "ticker": "AAA",
                "shares": "1e308",
                "entry_price": "1e308",
                "current_price": "1e-308",
            }
        ],
        cash="0",
    )

    with pytest.raises(
        PortfolioSnapshotIntegrityError,
        match="Portfolio analytics unavailable",
    ):
        compute_portfolio_analytics(snapshot)


def test_analytics_normalizes_unrepresentable_pnl_ratio_to_integrity_error():
    # The canonical snapshot fields are all finite and mutually consistent,
    # but the exact gain percentage is about 1e618 and cannot cross the
    # legacy float analytics schema. The direct API must degrade through its
    # one explicit integrity exception, never leak ValueError or infinity.
    snapshot = PortfolioSnapshot(
        positions=[
            PortfolioPosition(
                ticker="AAA",
                shares=1.0,
                entry_price=1e-308,
                current_price=1e308,
                market_value=1e308,
                unrealized_pnl_pct=float("inf"),
                is_leveraged_etf=False,
                shares_exact="1",
                entry_price_exact="1e-308",
                current_price_exact="1e308",
                market_value_exact="1e308",
            )
        ],
        cash=0.0,
        total_equity=1e308,
        as_of="2026-08-28",
        open_orders=[],
        open_orders_available=True,
        cash_exact="0",
        total_equity_exact="1e308",
    )

    with pytest.raises(
        PortfolioSnapshotIntegrityError,
        match="Portfolio analytics unavailable",
    ):
        compute_portfolio_analytics(snapshot)


def test_analytics_and_preview_revalidate_after_snapshot_mutation():
    snapshot = build_portfolio_snapshot(
        [
            {
                "ticker": "AAPL",
                "shares": "1",
                "entry_price": "100",
                "current_price": "100",
            }
        ],
        cash="900",
    )
    snapshot.positions[0].shares = 2

    with pytest.raises(PortfolioSnapshotIntegrityError):
        compute_portfolio_analytics(snapshot)
    with pytest.raises(PortfolioSnapshotIntegrityError):
        preview_trade_impact(
            snapshot,
            "AAPL",
            "sell",
            shares=1,
            reference_price=100,
        )


def test_estimate_pending_buy_value_by_ticker_matches_allocation_proposals_reexport():
    # assistant/allocation_proposals.py re-exports this from here for
    # backward compatibility (scripts/personal_assistant_ui.py imports it
    # from that module) -- must stay the same function, not a fork.
    from assistant.allocation_proposals import (
        estimate_pending_buy_value_by_ticker as reexported,
    )

    assert reexported is estimate_pending_buy_value_by_ticker
