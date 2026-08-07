"""Tests for assistant/portfolio_analytics.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.context_builder import build_portfolio_snapshot
from assistant.portfolio_analytics import (
    compute_portfolio_analytics,
    estimate_pending_buy_value_by_ticker,
    preview_trade_impact,
)


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


def test_estimate_pending_buy_value_by_ticker_matches_allocation_proposals_reexport():
    # assistant/allocation_proposals.py re-exports this from here for
    # backward compatibility (scripts/personal_assistant_ui.py imports it
    # from that module) -- must stay the same function, not a fork.
    from assistant.allocation_proposals import (
        estimate_pending_buy_value_by_ticker as reexported,
    )

    assert reexported is estimate_pending_buy_value_by_ticker
