import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.portfolio_ledger import (
    ACCOUNT_CASH,
    JournalTransaction,
    LedgerError,
    Posting,
    bootstrap_opening_snapshot,
    ledger_balances,
    post_transaction,
    reconcile_snapshot,
    sync_app_fills,
)
from assistant.schemas import PortfolioPosition, PortfolioSnapshot
from assistant.storage import AssistantStore


def _snapshot(cash=1000.0, shares=1.0):
    return PortfolioSnapshot(
        positions=[
            PortfolioPosition(
                ticker="AAPL",
                shares=shares,
                entry_price=100.0,
                current_price=110.0,
                market_value=shares * 110.0,
                unrealized_pnl_pct=10.0,
                is_leveraged_etf=False,
            )
        ],
        cash=cash,
        total_equity=cash + shares * 110.0,
        as_of="2026-07-29",
        source="alpaca",
        account_mode="paper",
    )


def test_unbalanced_transaction_is_rejected(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    transaction = JournalTransaction(
        transaction_id="bad",
        occurred_at="2026-07-29T12:00:00+00:00",
        source="test",
        external_id="bad",
        description="bad",
        postings=(Posting(ACCOUNT_CASH, Decimal("1")),),
    )
    with pytest.raises(LedgerError, match="not balanced"):
        post_transaction(store, transaction)


def test_bootstrap_sync_and_reconcile_are_idempotent(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    boot_at = datetime(2026, 7, 29, 10, tzinfo=timezone.utc)
    bootstrap_opening_snapshot(
        store, _snapshot(), confirmation="bootstrap", now=boot_at
    )
    balances = ledger_balances(store)
    assert balances["cash"] == Decimal("1000")
    assert balances["shares"]["AAPL"] == Decimal("1")
    with pytest.raises(LedgerError, match="non-empty"):
        bootstrap_opening_snapshot(
            store, _snapshot(), confirmation="bootstrap", now=boot_at
        )

    buy_at = boot_at + timedelta(hours=1)
    sell_at = boot_at + timedelta(hours=2)
    fills = [
        {
            "ticker": "AAPL",
            "side": "buy",
            "qty": 1.0,
            "price": 100.0,
            "at": buy_at.isoformat(),
            "fill_id": "fill-buy",
            "order_id": "order-buy",
            "proposal_id": "proposal-buy",
        }
    ]
    store.list_fills = lambda: fills
    first = sync_app_fills(store)
    assert first["inserted"] == 1
    assert sync_app_fills(store)["duplicates"] == 1
    balances = ledger_balances(store)
    assert balances["cash"] == Decimal("900")
    assert balances["shares"]["AAPL"] == Decimal("2")

    fills.append(
        {
            "ticker": "AAPL",
            "side": "sell",
            "qty": 1.0,
            "price": 120.0,
            "at": sell_at.isoformat(),
            "fill_id": "fill-sell",
            "order_id": "order-sell",
            "proposal_id": "proposal-sell",
        }
    )
    assert sync_app_fills(store)["inserted"] == 1
    balances = ledger_balances(store)
    assert balances["cash"] == Decimal("1020")
    assert balances["shares"]["AAPL"] == Decimal("1")
    assert balances["security_book_value"]["AAPL"] == Decimal("100")

    report = reconcile_snapshot(
        store, _snapshot(cash=1020.0, shares=1.0), now=sell_at
    )
    assert report["matched"] is True
    assert store.get_latest_ledger_reconciliation()["matched"] is True


def test_reconciliation_records_cash_and_position_mismatches(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    boot_at = datetime(2026, 7, 29, 10, tzinfo=timezone.utc)
    bootstrap_opening_snapshot(
        store, _snapshot(), confirmation="bootstrap", now=boot_at
    )
    report = reconcile_snapshot(
        store,
        _snapshot(cash=999.0, shares=2.0),
        now=boot_at + timedelta(minutes=1),
    )
    assert report["matched"] is False
    assert {item["kind"] for item in report["mismatches"]} == {
        "cash",
        "position",
    }
