import sys
import sqlite3
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
    SECURITY_ACCOUNT_PREFIX,
    JournalTransaction,
    LedgerError,
    Posting,
    _fill_transaction,
    bind_legacy_alpaca_account,
    bootstrap_opening_snapshot,
    ledger_balances,
    post_transaction,
    reconcile_snapshot,
    record_cash_transfer,
    record_dividend,
    record_fee,
    record_split,
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
        account_id="paper-account-1",
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


def test_reconciliation_rejects_a_different_broker_account(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    boot_at = datetime(2026, 7, 29, 10, tzinfo=timezone.utc)
    bootstrap_opening_snapshot(
        store, _snapshot(), confirmation="bootstrap", now=boot_at
    )
    wrong_account = _snapshot()
    wrong_account.account_id = "paper-account-2"

    with pytest.raises(LedgerError, match="does not match"):
        reconcile_snapshot(
            store, wrong_account, now=boot_at + timedelta(minutes=1)
        )


def test_legacy_account_binding_requires_an_exact_reconciliation(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    boot_at = datetime(2026, 7, 29, 10, tzinfo=timezone.utc)
    bootstrap_opening_snapshot(
        store, _snapshot(), confirmation="bootstrap", now=boot_at
    )
    legacy = store.get_system_state("ledger_bootstrap")
    legacy.pop("account_id")
    store.set_system_state("ledger_bootstrap", legacy)

    result = bind_legacy_alpaca_account(
        store,
        _snapshot(),
        confirmation="bind account",
        now=boot_at + timedelta(minutes=1),
    )
    assert result["already_bound"] is False
    assert result["account_id"] == "paper-account-1"
    assert (
        store.get_system_state("ledger_bootstrap")["account_id"]
        == "paper-account-1"
    )
    assert (
        store.get_latest_ledger_reconciliation()["broker"]["account_id"]
        == "paper-account-1"
    )


def test_legacy_account_binding_refuses_a_mismatch_without_binding(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    boot_at = datetime(2026, 7, 29, 10, tzinfo=timezone.utc)
    bootstrap_opening_snapshot(
        store, _snapshot(), confirmation="bootstrap", now=boot_at
    )
    legacy = store.get_system_state("ledger_bootstrap")
    legacy.pop("account_id")
    store.set_system_state("ledger_bootstrap", legacy)

    with pytest.raises(LedgerError, match="do not reconcile"):
        bind_legacy_alpaca_account(
            store,
            _snapshot(cash=999.0),
            confirmation="bind account",
            now=boot_at + timedelta(minutes=1),
        )
    assert "account_id" not in store.get_system_state("ledger_bootstrap")


def test_store_enables_foreign_keys_and_rejects_orphan_postings(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    with store._connect() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO journal_postings(
                    transaction_id, account, asset, amount, quantity,
                    metadata_json
                ) VALUES ('missing', 'cash', 'USD', '1', NULL, '{}')
                """
            )


def test_store_rejects_orphan_broker_order_updates(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    store.save_proposal(
        {
            "proposal_id": "tp-1",
            "created_at": "2026-07-30T12:00:00+00:00",
            "expires_at": "2026-07-31T12:00:00+00:00",
            "status": "broker_accepted",
            "idempotency_key": "idem-1",
            "intent": {
                "ticker": "AAPL",
                "side": "buy",
                "shares": 1,
                "order_type": "market",
                "limit_price": None,
            },
        }
    )
    with store._connect() as connection:
        connection.execute(
            """
            INSERT INTO broker_orders(
                order_id, proposal_id, submitted_at, status, payload_json
            ) VALUES ('order-1', 'tp-1', '2026-07-30T12:00:00+00:00',
                      'accepted', '{}')
            """
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                UPDATE broker_orders
                SET proposal_id = 'missing-proposal'
                WHERE order_id = 'order-1'
                """
            )


def test_integrity_check_detects_legacy_orphan_rows(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    # Simulate a row already present in a pre-hardening database. New writes
    # are protected by declared FKs and compatibility triggers, so the test
    # deliberately bypasses/removes the insert trigger using a raw legacy
    # connection.
    connection = sqlite3.connect(store.path)
    try:
        connection.execute("DROP TRIGGER fk_broker_orders_proposal_insert")
        connection.execute(
            """
            INSERT INTO broker_orders(
                order_id, proposal_id, submitted_at, status, payload_json
            ) VALUES ('legacy-orphan', 'missing-proposal',
                      '2026-07-30T12:00:00+00:00', 'accepted', '{}')
            """
        )
        connection.commit()
    finally:
        connection.close()

    results = store.database_integrity_check()
    assert results != ["ok"]
    assert any(
        "broker_orders.proposal_id" in result for result in results
    )


def test_broker_order_and_event_ids_cannot_be_rebound(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    for proposal_id in ("tp-1", "tp-2"):
        store.save_proposal(
            {
                "proposal_id": proposal_id,
                "created_at": "2026-07-30T12:00:00+00:00",
                "expires_at": "2026-07-31T12:00:00+00:00",
                "status": "submitting",
                "idempotency_key": f"idem-{proposal_id}",
                "intent": {
                    "ticker": "AAPL",
                    "side": "buy",
                    "shares": 1,
                    "order_type": "market",
                    "limit_price": None,
                },
            }
        )
    order = {
        "order_id": "order-1",
        "status": "accepted",
        "submitted_at": "2026-07-30T12:01:00+00:00",
        "filled_qty": 0,
    }
    store.project_broker_order_event(
        event_id="event-1",
        proposal_id="tp-1",
        order=order,
        event_type="new",
        event_at="2026-07-30T12:01:00+00:00",
        new_proposal_status="broker_accepted",
        expected_current_statuses=("submitting",),
        proposal_updates={"broker_order": order},
    )

    with pytest.raises(ValueError, match="already bound to proposal"):
        store.project_broker_order_event(
            event_id="event-2",
            proposal_id="tp-2",
            order=order,
            event_type="new",
            event_at="2026-07-30T12:02:00+00:00",
            new_proposal_status="broker_accepted",
            expected_current_statuses=("submitting",),
            proposal_updates={"broker_order": order},
        )

    second_order = dict(order, order_id="order-2")
    with pytest.raises(ValueError, match="event-1.*already bound"):
        store.project_broker_order_event(
            event_id="event-1",
            proposal_id="tp-2",
            order=second_order,
            event_type="new",
            event_at="2026-07-30T12:02:00+00:00",
            new_proposal_status="broker_accepted",
            expected_current_statuses=("submitting",),
            proposal_updates={"broker_order": second_order},
        )

    assert store.list_broker_orders()[0]["proposal_id"] == "tp-1"
    assert store.get_proposal("tp-2")["status"] == "submitting"


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

    assert record_dividend(
        store,
        external_id="div-2",
        ticker="aapl",
        gross_amount=5,
        occurred_at="2026-08-01T10:00:00+00:00",
        ex_date="2026-07-10",
        pay_date="2026-08-01",
        amount_per_share="0.25",
        shares_entitled="20",
        tax_classification="qualified",
    )
    enriched = _postings_for_account(store, ACCOUNT_DIVIDEND_INCOME)[1]
    assert enriched["metadata"]["ex_date"] == "2026-07-10"
    assert enriched["metadata"]["tax_classification"] == "qualified"

    with pytest.raises(LedgerError, match="must be positive"):
        record_dividend(
            store, external_id="div-bad", ticker="AAPL", gross_amount=0,
            occurred_at="2026-07-29T11:00:00+00:00",
        )
    with pytest.raises(LedgerError, match="does not match"):
        record_dividend(
            store,
            external_id="div-inconsistent",
            ticker="AAPL",
            gross_amount=10,
            occurred_at="2026-08-01T10:00:00+00:00",
            ex_date="2026-07-10",
            amount_per_share="0.25",
            shares_entitled="20",
        )


def test_record_split_changes_shares_without_changing_book_value(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    bootstrap_opening_snapshot(
        store,
        _snapshot(cash=1000, shares=2),
        confirmation="bootstrap",
        now=datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc),
    )
    before = ledger_balances(store)

    assert record_split(
        store,
        external_id="aapl-4-for-1",
        ticker="AAPL",
        ratio=4,
        occurred_at="2026-07-30T09:00:00+00:00",
    )
    after = ledger_balances(store)

    assert after["shares"]["AAPL"] == Decimal("8")
    assert (
        after["security_book_value"]["AAPL"]
        == before["security_book_value"]["AAPL"]
    )
    assert after["cash"] == before["cash"]
    # Provider retries are idempotent by external_id.
    assert not record_split(
        store,
        external_id="aapl-4-for-1",
        ticker="AAPL",
        ratio=4,
        occurred_at="2026-07-30T09:00:00+00:00",
    )


def test_split_is_blocked_while_a_pre_split_fill_is_still_unsynced(tmp_path):
    # Independent review, 2026-07-31: record_split() used to size its
    # adjustment purely off postings ALREADY in the journal. If ledger-sync
    # hadn't caught up on every pre-split fill yet (e.g. a delayed poll
    # picks up an old fill after the split was already recorded), the
    # adjustment posted against too few shares, and the late-arriving fill
    # then posted its ORIGINAL non-split-adjusted qty with no correction --
    # silently understating post-split share count. Must fail closed
    # instead of silently under-sizing the split.
    store = AssistantStore(tmp_path / "assistant.db")
    boot_at = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    # 2 shares are already journaled via the opening snapshot, so
    # held_at_effective is NOT zero -- the pre-existing "held 0 shares"
    # guard alone can't catch this case. A second, still-unsynced fill
    # (also dated before the split's effective time) is what must block it.
    bootstrap_opening_snapshot(
        store, _snapshot(shares=2.0), confirmation="bootstrap", now=boot_at
    )
    fills = [
        {
            "ticker": "AAPL", "side": "buy", "qty": 2.0, "price": 100.0,
            "at": (boot_at + timedelta(days=5)).isoformat(), "fill_id": "f-early",
        },
    ]
    store.list_fills = lambda: fills
    # Deliberately never ran sync_app_fills() -- this fill is still
    # unsynced when the split effective date arrives.
    with pytest.raises(LedgerError, match="have not been journaled yet"):
        record_split(
            store,
            external_id="aapl-4-for-1-early",
            ticker="AAPL",
            ratio=4,
            occurred_at="2026-07-15T09:00:00+00:00",
        )

    # Once synced, the same split proceeds correctly against the full
    # (2 + 2 = 4) pre-split count, not just the 2 that were already journaled.
    sync_app_fills(store)
    assert record_split(
        store,
        external_id="aapl-4-for-1-early",
        ticker="AAPL",
        ratio=4,
        occurred_at="2026-07-15T09:00:00+00:00",
    )
    assert ledger_balances(store)["shares"]["AAPL"] == Decimal("16")


def test_retroactive_split_uses_shares_at_effective_time(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    bootstrap_opening_snapshot(
        store,
        _snapshot(cash=1000, shares=2),
        confirmation="bootstrap",
        now=datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
    )
    # A later quantity-only journal event represents one post-split share
    # leaving the account. Recording the earlier split afterward must adjust
    # the two shares held on July 15, not the one share held today.
    assert post_transaction(
        store,
        JournalTransaction(
            transaction_id="later-share-disposal",
            occurred_at="2026-07-20T09:00:00+00:00",
            source="test_quantity_event",
            external_id="later-share-disposal",
            description="Later share disposal",
            postings=(
                Posting(
                    SECURITY_ACCOUNT_PREFIX + "AAPL",
                    Decimal("0"),
                    quantity=Decimal("-1"),
                ),
            ),
        ),
    )

    assert record_split(
        store,
        external_id="aapl-4-for-1-retroactive",
        ticker="AAPL",
        ratio=4,
        occurred_at="2026-07-15T09:00:00+00:00",
    )

    assert ledger_balances(store)["shares"]["AAPL"] == Decimal("7")


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
