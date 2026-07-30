import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.portfolio_ledger import (
    ACCOUNT_CASH,
    ACCOUNT_CONTRIBUTED_CAPITAL,
    ACCOUNT_DIVIDEND_INCOME,
    ACCOUNT_FEES,
    ACCOUNT_REALIZED_PNL,
    JournalTransaction,
    LedgerError,
    Posting,
    _fill_transaction,
    bootstrap_opening_snapshot,
    ledger_balances,
    post_transaction,
    reconcile_snapshot,
    record_cash_transfer,
    record_dividend,
    record_fee,
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


def _postings_for_account(store: AssistantStore, account: str) -> list[dict]:
    return [row for row in store.list_journal_postings() if row["account"] == account]


def test_realized_pnl_and_dividend_income_post_with_the_credit_normal_sign(tmp_path):
    # Independent review, 2026-07-30: the sign convention (equity/income
    # accounts post NEGATIVE when they increase, matching standard
    # credit-normal double-entry accounting) is correct but was
    # undocumented and easy to misread as backwards -- nothing else in
    # this codebase yet reads a realized-P&L figure to sanity-check
    # against. Locks the actual sign in so a future refactor can't
    # silently flip it: a $20 GAIN must post as -20, not +20.
    store = AssistantStore(tmp_path / "assistant.db")
    boot_at = datetime(2026, 7, 29, 10, tzinfo=timezone.utc)
    bootstrap_opening_snapshot(
        store, _snapshot(shares=0.0), confirmation="bootstrap", now=boot_at
    )
    fills = [
        {
            "ticker": "AAPL", "side": "buy", "qty": 1.0, "price": 100.0,
            "at": (boot_at + timedelta(hours=1)).isoformat(), "fill_id": "f-buy",
        },
    ]
    store.list_fills = lambda: fills
    sync_app_fills(store)

    fills.append(
        {
            "ticker": "AAPL", "side": "sell", "qty": 1.0, "price": 120.0,
            "at": (boot_at + timedelta(hours=2)).isoformat(), "fill_id": "f-sell-gain",
        }
    )
    sync_app_fills(store)
    pnl_postings = _postings_for_account(store, ACCOUNT_REALIZED_PNL)
    assert len(pnl_postings) == 1
    assert Decimal(pnl_postings[0]["amount"]) == Decimal("-20")  # sold $20 above cost -> a GAIN posts negative


def test_selling_more_shares_than_held_is_rejected(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    boot_at = datetime(2026, 7, 29, 10, tzinfo=timezone.utc)
    bootstrap_opening_snapshot(
        store, _snapshot(shares=1.0), confirmation="bootstrap", now=boot_at
    )
    fills = [
        {
            "ticker": "AAPL", "side": "sell", "qty": 5.0, "price": 100.0,
            "at": (boot_at + timedelta(hours=1)).isoformat(), "fill_id": "f-oversell",
        },
    ]
    store.list_fills = lambda: fills
    with pytest.raises(LedgerError, match="ledger holds"):
        sync_app_fills(store)


def test_selling_with_no_position_held_is_rejected(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    boot_at = datetime(2026, 7, 29, 10, tzinfo=timezone.utc)
    bootstrap_opening_snapshot(
        store, _snapshot(shares=0.0), confirmation="bootstrap", now=boot_at
    )
    fills = [
        {
            "ticker": "AAPL", "side": "sell", "qty": 1.0, "price": 100.0,
            "at": (boot_at + timedelta(hours=1)).isoformat(), "fill_id": "f-sell-none",
        },
    ]
    store.list_fills = lambda: fills
    with pytest.raises(LedgerError, match="ledger holds"):
        sync_app_fills(store)


def test_fill_transaction_rejects_invalid_side_or_non_positive_values():
    balances = {"shares": {}, "security_book_value": {}}
    base = {
        "ticker": "AAPL", "qty": 1.0, "price": 100.0,
        "at": "2026-07-29T10:00:00+00:00", "fill_id": "f1",
    }

    with pytest.raises(LedgerError, match="invalid fill"):
        _fill_transaction(fill=dict(base, side="hold"), balances=balances)
    with pytest.raises(LedgerError, match="invalid fill"):
        _fill_transaction(fill=dict(base, side="buy", qty=0.0), balances=balances)
    with pytest.raises(LedgerError, match="invalid fill"):
        _fill_transaction(fill=dict(base, side="buy", price=-5.0), balances=balances)


def test_record_cash_transfer_deposit_and_withdrawal_are_idempotent(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    assert record_cash_transfer(
        store, external_id="deposit-1", amount=500.0,
        occurred_at="2026-07-29T10:00:00+00:00", description="Initial deposit",
    ) is True
    assert ledger_balances(store)["cash"] == Decimal("500")
    capital_postings = _postings_for_account(store, ACCOUNT_CONTRIBUTED_CAPITAL)
    assert Decimal(capital_postings[0]["amount"]) == Decimal("-500")  # offsetting equity leg

    assert record_cash_transfer(
        store, external_id="withdrawal-1", amount=-200.0,
        occurred_at="2026-07-29T11:00:00+00:00", description="Withdrawal",
    ) is True
    assert ledger_balances(store)["cash"] == Decimal("300")

    # Re-posting the SAME external_id is a safe idempotent no-op, not a duplicate.
    assert record_cash_transfer(
        store, external_id="deposit-1", amount=500.0,
        occurred_at="2026-07-29T10:00:00+00:00", description="Initial deposit",
    ) is False
    assert ledger_balances(store)["cash"] == Decimal("300")

    with pytest.raises(LedgerError, match="cannot be zero"):
        record_cash_transfer(
            store, external_id="deposit-zero", amount=0,
            occurred_at="2026-07-29T12:00:00+00:00", description="Zero transfer",
        )


def test_record_dividend(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    assert record_dividend(
        store, external_id="div-1", ticker="aapl", gross_amount=12.34,
        occurred_at="2026-07-29T10:00:00+00:00",
    ) is True
    assert ledger_balances(store)["cash"] == Decimal("12.34")
    dividend_postings = _postings_for_account(store, ACCOUNT_DIVIDEND_INCOME)
    assert Decimal(dividend_postings[0]["amount"]) == Decimal("-12.34")
    assert dividend_postings[0]["metadata"]["ticker"] == "AAPL"

    with pytest.raises(LedgerError, match="must be positive"):
        record_dividend(
            store, external_id="div-bad", ticker="AAPL", gross_amount=0,
            occurred_at="2026-07-29T11:00:00+00:00",
        )


def test_record_fee(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    assert record_fee(
        store, external_id="fee-1", amount=1.5,
        occurred_at="2026-07-29T10:00:00+00:00", description="Regulatory fee",
    ) is True
    assert ledger_balances(store)["cash"] == Decimal("-1.5")
    fee_postings = _postings_for_account(store, ACCOUNT_FEES)
    assert Decimal(fee_postings[0]["amount"]) == Decimal("1.5")

    with pytest.raises(LedgerError, match="must be positive"):
        record_fee(
            store, external_id="fee-bad", amount=-1,
            occurred_at="2026-07-29T11:00:00+00:00", description="Bad fee",
        )
