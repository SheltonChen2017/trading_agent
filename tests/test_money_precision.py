"""Regression tests for M7: execution money must not use float arithmetic."""
from __future__ import annotations

import sqlite3
from decimal import Decimal, localcontext

import pytest

from assistant.context_builder import build_portfolio_snapshot
from assistant.money import decimal_text, to_decimal
from assistant.storage import AssistantStore
from risk.execution_gate import TradeIntent, validate_trade_intent


def _save_budget_proposal(store: AssistantStore, proposal_id: str) -> None:
    store.save_proposal(
        {
            "proposal_id": proposal_id,
            "created_at": "2026-07-30T12:00:00+00:00",
            "expires_at": "2026-07-31T12:00:00+00:00",
            "status": "filled",
            "idempotency_key": f"idem-{proposal_id}",
            "intent": {
                "ticker": proposal_id.upper(),
                "side": "buy",
                "shares": 1,
                "order_type": "market",
                "limit_price": None,
            },
        }
    )


def test_decimal_conversion_uses_visible_value_not_binary_expansion():
    assert to_decimal(0.1) == Decimal("0.1")
    assert to_decimal(0.1) + to_decimal(0.2) == Decimal("0.3")
    assert decimal_text(Decimal("3.0500")) == "3.05"


def test_daily_reservation_accepts_exact_float_boundary(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    for proposal_id in ("p-1", "p-2", "p-3"):
        _save_budget_proposal(store, proposal_id)

    store.reserve_execution_budget(
        "p-1",
        trading_day="2026-07-30",
        notional=0.1,
        max_daily_notional=0.3,
        max_daily_orders=10,
    )
    second = store.reserve_execution_budget(
        "p-2",
        trading_day="2026-07-30",
        notional=0.2,
        max_daily_notional=0.3,
        max_daily_orders=10,
    )

    assert second["daily_reserved_notional_decimal"] == "0.3"
    usage = store.get_execution_budget_usage("2026-07-30")
    assert usage["submitted_notional_decimal"] == "0.3"
    assert usage["submitted_notional"] == 0.3  # legacy JSON-facing shape

    with pytest.raises(ValueError, match="Daily submitted notional"):
        store.reserve_execution_budget(
            "p-3",
            trading_day="2026-07-30",
            notional="0.0001",
            max_daily_notional="0.3",
            max_daily_orders=10,
        )


def test_daily_reservation_refuses_exact_overage_under_low_ambient_precision(
    tmp_path,
):
    store = AssistantStore(tmp_path / "assistant.db")
    _save_budget_proposal(store, "p-over")

    with localcontext() as context:
        context.prec = 3
        with pytest.raises(ValueError, match="Daily submitted notional"):
            store.reserve_execution_budget(
                "p-over",
                trading_day="2026-07-30",
                notional="12.1401",
                max_daily_notional="12.12",
                max_daily_orders=10,
            )

    usage = store.get_execution_budget_usage("2026-07-30")
    assert usage["submitted_order_count"] == 0
    assert usage["submitted_notional_decimal"] == "0"


def test_budget_usage_sum_ignores_lowered_ambient_decimal_precision(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    for proposal_id, notional in (("p-1", "12.1401"), ("p-2", "0.0009")):
        _save_budget_proposal(store, proposal_id)
        store.reserve_execution_budget(
            proposal_id,
            trading_day="2026-07-30",
            notional=notional,
            max_daily_notional="100",
            max_daily_orders=10,
        )

    with localcontext() as context:
        context.prec = 3
        usage = store.get_execution_budget_usage("2026-07-30")

    assert usage["submitted_notional_decimal"] == "12.141"


def test_legacy_real_reservations_are_backfilled_to_exact_text(tmp_path):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE execution_reservations (
            proposal_id TEXT PRIMARY KEY,
            trading_day TEXT NOT NULL,
            reserved_notional REAL NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "INSERT INTO execution_reservations VALUES (?, ?, ?, ?)",
        ("legacy-1", "2026-07-30", 0.3, "2026-07-30T00:00:00+00:00"),
    )
    connection.commit()
    connection.close()

    store = AssistantStore(path)
    with sqlite3.connect(path) as migrated:
        exact = migrated.execute(
            "SELECT reserved_notional_text FROM execution_reservations "
            "WHERE proposal_id = 'legacy-1'"
        ).fetchone()[0]

    assert exact == "0.3"
    assert (
        store.get_execution_budget_usage("2026-07-30")[
            "submitted_notional_decimal"
        ]
        == "0.3"
    )


def test_cash_and_max_order_checks_do_not_reject_exact_boundary():
    portfolio = build_portfolio_snapshot([], cash="0.3", buying_power="0.3")
    result = validate_trade_intent(
        TradeIntent(ticker="KO", side="buy", shares=3),
        portfolio,
        reference_price=0.1,
        max_order_value=0.3,
        max_position_pct=1.0,
        max_total_exposure_pct=1.0,
        max_basket_pct=100.0,
        max_leveraged_etf_pct=100.0,
        min_cash_reserve_pct=0.0,
    )

    assert result.approved, result.violations


def test_pending_exposure_sum_does_not_cross_exact_percentage_boundary():
    portfolio = build_portfolio_snapshot([], cash="1.0", buying_power="1.0")
    result = validate_trade_intent(
        TradeIntent(ticker="KO", side="buy", shares=1),
        portfolio,
        reference_price=0.1,
        pending_buy_value_by_ticker={"KO": 0.2},
        max_order_value=1.0,
        max_position_pct=0.3,
        max_total_exposure_pct=0.3,
        max_basket_pct=100.0,
        max_leveraged_etf_pct=100.0,
        min_cash_reserve_pct=0.0,
    )

    assert result.approved, result.violations


def test_sell_exceeds_held_uses_exact_broker_quantity_not_rounded_float():
    portfolio = build_portfolio_snapshot(
        [
            {
                "ticker": "ABC",
                "shares": "10.999999999999999999",
                "entry_price": "1",
                "current_price": "1",
            }
        ],
        cash="1",
    )
    assert portfolio.positions[0].shares == 11.0  # lossy display field
    assert portfolio.positions[0].shares_exact == "10.999999999999999999"

    result = validate_trade_intent(
        TradeIntent(ticker="ABC", side="sell", shares=11),
        portfolio,
        reference_price=1,
        max_order_value=5_000,
        max_position_pct=1.0,
        max_total_exposure_pct=1.0,
        max_basket_pct=100.0,
        max_leveraged_etf_pct=100.0,
        min_cash_reserve_pct=0.0,
    )

    assert not result.approved
    assert "sell_exceeds_held" in result.violation_codes


def test_snapshot_aggregates_decimal_broker_strings_before_display_rounding():
    snapshot = build_portfolio_snapshot(
        [
            {
                "ticker": "ABC",
                "shares": "1",
                "entry_price": "0.1",
                "current_price": "0.1",
            },
            {
                "ticker": "ABC",
                "shares": "1",
                "entry_price": "0.2",
                "current_price": "0.1",
            },
        ],
        cash="0.1",
        buying_power="0.1",
    )

    assert snapshot.cash_decimal == Decimal("0.1")
    assert snapshot.total_equity_decimal == Decimal("0.3")
    assert snapshot.positions[0].entry_price_decimal == Decimal("0.15")
    assert snapshot.positions[0].market_value_decimal == Decimal("0.2")
