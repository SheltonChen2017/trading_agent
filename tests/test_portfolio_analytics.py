"""Tests for assistant/portfolio_analytics.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.context_builder import build_portfolio_snapshot
from assistant.portfolio_analytics import (
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


def test_estimate_pending_buy_value_by_ticker_matches_allocation_proposals_reexport():
    # assistant/allocation_proposals.py re-exports this from here for
    # backward compatibility (scripts/personal_assistant_ui.py imports it
    # from that module) -- must stay the same function, not a fork.
    from assistant.allocation_proposals import (
        estimate_pending_buy_value_by_ticker as reexported,
    )

    assert reexported is estimate_pending_buy_value_by_ticker
