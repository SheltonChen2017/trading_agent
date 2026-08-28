import sys
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from assistant.tax_lots import MARKET_TIMEZONE
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
    _ACTIVITY_EXTERNAL_ID_PREFIXES,
    _HANDLED_ACTIVITY_TYPES,
    _assert_broker_activity_id_not_retyped,
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
    sync_broker_activities,
    acknowledge_broker_activity,
)
from assistant.dispatch_fence import get_runtime_emergency_stop
from assistant.storage import (
    BrokerActivityAcknowledgementConflictError,
    BrokerOrderBindingConflictError,
    JournalTransactionConflictError,
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


def test_bootstrap_rolls_back_journal_when_state_write_fails(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    with store._connect() as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_ledger_bootstrap_state
            BEFORE INSERT ON system_state
            WHEN NEW.state_key = 'ledger_bootstrap'
            BEGIN
                SELECT RAISE(ABORT, 'injected bootstrap state failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="injected bootstrap"):
        bootstrap_opening_snapshot(
            store,
            _snapshot(),
            confirmation="bootstrap",
            now=datetime(2026, 7, 29, 10, tzinfo=timezone.utc),
        )

    assert store.get_system_state("ledger_bootstrap") is None
    assert store.list_journal_postings() == []


def test_concurrent_different_bootstraps_have_one_atomic_winner(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    original_get_system_state = store.get_system_state
    both_passed_preflight = threading.Barrier(2)

    def synchronized_get_system_state(key, default=None):
        if key == "ledger_bootstrap":
            both_passed_preflight.wait(timeout=5)
        return original_get_system_state(key, default)

    store.get_system_state = synchronized_get_system_state
    snapshots = [_snapshot(cash=1000.0), _snapshot(cash=2000.0)]
    results = []
    result_lock = threading.Lock()

    def bootstrap(snapshot):
        try:
            state = bootstrap_opening_snapshot(
                store,
                snapshot,
                confirmation="bootstrap",
                now=datetime(2026, 7, 29, 10, tzinfo=timezone.utc),
            )
            result = ("saved", state)
        except LedgerError as exc:
            result = ("rejected", str(exc))
        with result_lock:
            results.append(result)

    threads = [threading.Thread(target=bootstrap, args=(snapshot,)) for snapshot in snapshots]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(result[0] for result in results) == ["rejected", "saved"]
    store.get_system_state = original_get_system_state
    postings = store.list_journal_postings()
    assert {row["transaction_id"] for row in postings} == {
        f"opening-{store.get_system_state('ledger_bootstrap')['snapshot_hash'][:24]}"
    }


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

    with pytest.raises(
        BrokerOrderBindingConflictError,
        match="already bound to proposal",
    ):
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
    with pytest.raises(
        JournalTransactionConflictError,
        match="event-1.*already bound",
    ):
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

    orders = store.list_broker_orders()
    assert len(orders) == 1
    assert orders[0]["proposal_id"] == "tp-1"
    assert orders[0]["order_id"] == "order-1"
    events = store.list_broker_order_events()
    assert len(events) == 1
    assert events[0]["event_id"] == "event-1"
    assert events[0]["proposal_id"] == "tp-1"
    assert events[0]["order_id"] == "order-1"
    second = store.get_proposal("tp-2")
    assert second["status"] == "submission_unknown"
    assert "existing broker projection was retained" in second["error"]
    assert store.get_kill_switch()["active"] is True
    assert get_runtime_emergency_stop(store.path)["active"] is True
    alert_categories = {
        alert["category"] for alert in store.list_operational_alerts(status="open")
    }
    assert alert_categories == {"broker_order_binding", "broker_event_integrity"}


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


def test_conflicting_external_id_is_rejected_not_treated_as_a_retry(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    assert record_cash_transfer(
        store,
        external_id="bank-1",
        amount=500.0,
        occurred_at="2026-07-29T10:00:00+00:00",
        description="Deposit",
    )

    with pytest.raises(LedgerError, match="external_id.*different content"):
        record_cash_transfer(
            store,
            external_id="bank-1",
            amount=5_000.0,
            occurred_at="2026-07-29T10:00:00+00:00",
            description="Deposit",
        )

    assert ledger_balances(store)["cash"] == Decimal("500")


def test_dividend_and_fee_external_ids_reject_changed_content(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    assert record_dividend(
        store,
        external_id="div-conflict",
        ticker="AAPL",
        gross_amount=10,
        occurred_at="2026-07-29T10:00:00+00:00",
    )
    with pytest.raises(LedgerError, match="different content"):
        record_dividend(
            store,
            external_id="div-conflict",
            ticker="AAPL",
            gross_amount=20,
            occurred_at="2026-07-29T10:00:00+00:00",
        )

    assert record_fee(
        store,
        external_id="fee-conflict",
        amount=1,
        occurred_at="2026-07-29T11:00:00+00:00",
        description="Regulatory fee",
    )
    with pytest.raises(LedgerError, match="different content"):
        record_fee(
            store,
            external_id="fee-conflict",
            amount=2,
            occurred_at="2026-07-29T11:00:00+00:00",
            description="Regulatory fee",
        )


def test_split_external_id_rejects_a_changed_ratio(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    bootstrap_opening_snapshot(
        store,
        _snapshot(shares=2),
        confirmation="bootstrap",
        now=datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc),
    )
    assert record_split(
        store,
        external_id="split-conflict",
        ticker="AAPL",
        ratio=4,
        occurred_at="2026-07-30T09:00:00+00:00",
    )
    with pytest.raises(LedgerError, match="different content"):
        record_split(
            store,
            external_id="split-conflict",
            ticker="AAPL",
            ratio=3,
            occurred_at="2026-07-30T09:00:00+00:00",
        )


def test_app_fill_external_id_rejects_changed_execution_content(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    boot_at = datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc)
    bootstrap_opening_snapshot(
        store, _snapshot(shares=0), confirmation="bootstrap", now=boot_at
    )
    fill = {
        "ticker": "AAPL",
        "side": "buy",
        "qty": 1,
        "price": 100,
        "at": (boot_at + timedelta(hours=1)).isoformat(),
        "fill_id": "fill-conflict",
        "order_id": "order-1",
        "proposal_id": "proposal-1",
    }
    store.list_fills = lambda: [fill]
    assert sync_app_fills(store)["inserted"] == 1

    store.list_fills = lambda: [{**fill, "price": 200}]
    with pytest.raises(LedgerError, match="different content"):
        sync_app_fills(store)


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


# --- sync_broker_activities() (broker-activity ingestion, 2026-08-10) ---
# Motivating incident: Alpaca posts CAT fees on paper accounts as
# non-trade account activities, which nothing ingested, so the ledger
# drifted 1 cent per fee day and nightly reconciliation failed forever
# with an unexplained cash mismatch (74389.33 ledger vs 74389.30 broker).


def _fee_activity(
    activity_id="20260729000000000::fee-a",
    created_at="2026-07-29T11:00:00Z",
    net_amount="-0.01",
    **overrides,
):
    activity = {
        "id": activity_id,
        "activity_type": "FEE",
        "activity_sub_type": "CAT",
        "created_at": created_at,
        "currency": "USD",
        "date": "2026-07-28",
        "description": "CAT fee for proceed of 2 trades on 2026-07-28",
        "net_amount": net_amount,
        "status": "executed",
    }
    activity.update(overrides)
    return activity


def _bootstrapped_store(tmp_path, cash=1000.0):
    store = AssistantStore(tmp_path / "assistant.db")
    boot_at = datetime(2026, 7, 29, 10, tzinfo=timezone.utc)
    bootstrap_opening_snapshot(
        store, _snapshot(cash=cash), confirmation="bootstrap", now=boot_at
    )
    return store, boot_at


def test_sync_broker_activities_posts_fees_idempotently(tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    activities = [_fee_activity()]
    first = sync_broker_activities(store, activities)
    assert first["inserted"] == 1
    assert first["duplicates"] == 0
    assert ledger_balances(store)["cash"] == Decimal("999.99")
    replay = sync_broker_activities(store, activities)
    assert replay["inserted"] == 0
    assert replay["duplicates"] == 1
    assert ledger_balances(store)["cash"] == Decimal("999.99")
    fee_postings = _postings_for_account(store, ACCOUNT_FEES)
    assert len(fee_postings) == 1
    assert Decimal(fee_postings[0]["amount"]) == Decimal("0.01")


def test_sync_broker_activities_skips_fees_already_in_opening_cash(tmp_path):
    # The double-posting trap: an activity POSTED at or before the
    # bootstrap instant is already inside opening cash, even when its
    # date label is later. Re-posting it would push the ledger BELOW the
    # broker, the opposite failure of the one this sync fixes.
    store, boot_at = _bootstrapped_store(tmp_path)
    report = sync_broker_activities(
        store,
        [
            _fee_activity(
                activity_id="a::before", created_at="2026-07-29T09:00:00Z"
            ),
            _fee_activity(
                activity_id="a::exactly-at-boot",
                created_at=boot_at.isoformat(),
            ),
            _fee_activity(activity_id="a::after", created_at="2026-07-29T10:00:01Z"),
        ],
    )
    assert report["skipped_pre_bootstrap"] == 2
    assert report["inserted"] == 1
    assert ledger_balances(store)["cash"] == Decimal("999.99")


def test_sync_broker_activities_skips_all_pre_bootstrap_nontrade_types(tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    dividend = {
        "id": "20260729090000000::div-before",
        "activity_type": "DIV",
        "created_at": "2026-07-29T09:00:00Z",
        "date": "2026-07-29",
        "net_amount": "12.48",
    }
    report = sync_broker_activities(store, [dividend])
    assert report["skipped_pre_bootstrap"] == 1
    assert report["inserted"] == 0
    assert ledger_balances(store)["cash"] == Decimal("1000")


def test_sync_broker_activities_accepts_documented_minimal_fee_shape(tmp_path):
    store, boot_at = _bootstrapped_store(tmp_path)
    activity = _fee_activity(
        activity_id="20260729110000000::fee-minimal",
        created_at=None,
    )
    for undocumented_field in ("created_at", "status", "currency"):
        activity.pop(undocumented_field, None)

    report = sync_broker_activities(
        store, [activity], created_after=boot_at
    )

    assert report["inserted"] == 1
    assert ledger_balances(store)["cash"] == Decimal("999.99")


def test_sync_broker_activities_rejects_an_unverified_created_after_bound(tmp_path):
    store, boot_at = _bootstrapped_store(tmp_path)
    activity = _fee_activity(created_at=None)
    activity.pop("created_at")
    with pytest.raises(LedgerError, match="must match the ledger bootstrap"):
        sync_broker_activities(
            store,
            [activity],
            created_after=boot_at + timedelta(seconds=1),
        )


def test_sync_broker_activities_refuses_unknown_activity_types(tmp_path):
    # Contract update 2026-08-10: plain DIV was this test's original
    # unknown-type example; it is now deliberately handled (see the DIV
    # tests below), so INT stands in as the unhandled case. The invariant
    # this test pins is unchanged: an unrecognized activity must block
    # evidence capture loudly, not be skipped into a silent cash drift,
    # while the recognized fee in the same batch is still journaled --
    # posting is idempotent, so no work is lost, and the observation stays
    # blocked until the sync is deliberately extended.
    store, _ = _bootstrapped_store(tmp_path)
    interest = {
        "id": "int::1",
        "activity_type": "INT",
        "created_at": "2026-07-29T12:00:00Z",
        "date": "2026-07-29",
        "net_amount": "12.48",
        "status": "executed",
    }
    with pytest.raises(LedgerError, match="unhandled activity type INT"):
        sync_broker_activities(store, [_fee_activity(), interest])
    assert ledger_balances(store)["cash"] == Decimal("999.99")


def test_sync_broker_activities_refuses_malformed_fees(tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    cases = [
        (_fee_activity(net_amount="0.01"), "non-negative net_amount"),
        (_fee_activity(net_amount="0"), "non-negative net_amount"),
        (_fee_activity(net_amount=None), "not numeric"),
        (
            _fee_activity(activity_id="not-a-timestamped-id", created_at=None),
            "posting time is missing",
        ),
        (_fee_activity(created_at="2026-07-29T11:00:00"), "must include a timezone"),
        (_fee_activity(status="correction"), "not executed"),
        (_fee_activity(activity_id=None), "missing its broker id"),
    ]
    for activity, match in cases:
        with pytest.raises(LedgerError, match=match):
            sync_broker_activities(store, [activity])
    assert ledger_balances(store)["cash"] == Decimal("1000")


def test_sync_broker_activities_skips_trade_activities(tmp_path):
    # Fills reach the journal through the app's own fill records; a fill
    # the app never saw must surface as a share mismatch in
    # reconcile_snapshot, not be absorbed from the broker feed here.
    store, _ = _bootstrapped_store(tmp_path)
    fill = {
        "id": "fill::1",
        "activity_type": "FILL",
        "transaction_time": "2026-07-29T14:00:00Z",
        "price": "100.0",
        "qty": "1",
        "side": "buy",
        "symbol": "AAPL",
    }
    report = sync_broker_activities(store, [fill])
    assert report["trade_activities_skipped"] == 1
    assert report["inserted"] == 0
    assert ledger_balances(store)["cash"] == Decimal("1000")


def test_sync_broker_activities_requires_bootstrap(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    with pytest.raises(LedgerError, match="bootstrap the portfolio journal"):
        sync_broker_activities(store, [_fee_activity()])


def test_sync_broker_activities_restores_reconciliation_match(tmp_path):
    # Miniature of the real incident: three post-bootstrap CAT fees the
    # broker already deducted. Before the sync the reconciliation must
    # fail (0.03 > CASH_TOLERANCE); after it, match exactly.
    store, _ = _bootstrapped_store(tmp_path, cash=1000.0)
    broker_now = _snapshot(cash=999.97)
    before = reconcile_snapshot(store, broker_now)
    assert before["matched"] is False
    assert before["mismatches"][0]["kind"] == "cash"
    fees = [
        _fee_activity(
            activity_id=f"cat::{day}",
            created_at=f"2026-07-{day}T00:06:00Z",
        )
        for day in (30, 31)
    ] + [_fee_activity(activity_id="cat::aug", created_at="2026-08-01T00:06:00Z")]
    report = sync_broker_activities(store, fees)
    assert report["inserted"] == 3
    after = reconcile_snapshot(store, broker_now)
    assert after["matched"] is True
    assert ledger_balances(store)["cash"] == Decimal("999.97")


# --- DIV / cash-movement handling in sync_broker_activities (2026-08-10) ---
# Motivating deadline: the account bought 39 AEP on 2026-08-07, before the
# 2026-08-10 record/ex-date, so a $37.05 cash dividend is scheduled to arrive
# as a DIV activity on the 2026-09-10 pay date. Without a handler it fails and
# stalls the epoch exactly like the CAT fees did (watch item CR-W2).


def _div_activity(**overrides):
    activity = {
        "id": "20260910000000000::div-aep",
        "activity_type": "DIV",
        "created_at": "2026-07-29T11:30:00Z",
        "date": "2026-07-29",
        "net_amount": "37.05",
        "per_share_amount": "0.95",
        "qty": "39",
        "symbol": "AEP",
        "status": "executed",
    }
    activity.update(overrides)
    return activity


def test_sync_broker_activities_posts_a_plain_dividend_idempotently(tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    report = sync_broker_activities(store, [_div_activity()])
    assert report["inserted"] == 1
    assert report["by_type"] == {"DIV": {"inserted": 1, "duplicates": 0}}
    assert ledger_balances(store)["cash"] == Decimal("1037.05")
    income = _postings_for_account(store, ACCOUNT_DIVIDEND_INCOME)
    assert len(income) == 1
    assert Decimal(income[0]["amount"]) == Decimal("-37.05")
    transaction = store.get_journal_transaction_by_external_id(
        "dividend:20260910000000000::div-aep"
    )
    assert transaction["metadata"]["tax_classification"] == "unknown"
    assert transaction["metadata"]["ticker"] == "AEP"
    assert "pay_date" not in transaction["metadata"]
    # Market-local midnight (DHCR-001), which is 04:00Z during EDT.
    assert transaction["occurred_at"] == "2026-07-29T04:00:00+00:00"
    assert _market_local_date(transaction["occurred_at"]) == "2026-07-29"
    replay = sync_broker_activities(store, [_div_activity()])
    assert replay["duplicates"] == 1
    assert ledger_balances(store)["cash"] == Decimal("1037.05")


def test_sync_broker_activities_dividend_without_optional_fields(tmp_path):
    # Alpaca's published schema does not promise per_share_amount/qty.
    store, _ = _bootstrapped_store(tmp_path)
    minimal = _div_activity()
    for optional in ("per_share_amount", "qty", "status", "date"):
        minimal.pop(optional)
    report = sync_broker_activities(store, [minimal])
    assert report["inserted"] == 1
    assert ledger_balances(store)["cash"] == Decimal("1037.05")


def test_sync_broker_activities_refuses_malformed_dividends(tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    cases = [
        (_div_activity(net_amount="-37.05"), "non-positive net_amount"),
        (_div_activity(net_amount="0"), "non-positive net_amount"),
        (_div_activity(symbol=None), "missing its symbol"),
        (_div_activity(symbol="BAD:TICKER"), "invalid ticker"),
        # per_share x qty must reconcile with the cash amount; a broker row
        # that contradicts its own arithmetic is refused, not averaged.
        (_div_activity(per_share_amount="0.50"), "does not match"),
        (_div_activity(qty="banana"), "must be numeric"),
    ]
    for activity, match in cases:
        with pytest.raises(LedgerError, match=match):
            sync_broker_activities(store, [activity])
    assert ledger_balances(store)["cash"] == Decimal("1000")


def test_sync_broker_activities_posts_cash_movements_with_signed_amounts(tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    deposit = {
        "id": "csd::top-up",
        "activity_type": "CSD",
        "created_at": "2026-07-29T12:00:00Z",
        "net_amount": "500",
        "status": "executed",
    }
    withdrawal = {
        "id": "csw::out",
        "activity_type": "CSW",
        "created_at": "2026-07-29T12:30:00Z",
        "net_amount": "-200",
        "status": "executed",
    }
    report = sync_broker_activities(store, [deposit, withdrawal])
    assert report["inserted"] == 2
    assert report["by_type"] == {
        "CSD": {"inserted": 1, "duplicates": 0},
        "CSW": {"inserted": 1, "duplicates": 0},
    }
    balances = ledger_balances(store)
    assert balances["cash"] == Decimal("1300")
    capital = _postings_for_account(store, ACCOUNT_CONTRIBUTED_CAPITAL)
    assert sorted(Decimal(row["amount"]) for row in capital) == [
        Decimal("-500"),
        Decimal("200"),
    ]
    assert sync_broker_activities(store, [deposit, withdrawal])["duplicates"] == 2


def test_sync_broker_activities_refuses_wrong_sign_cash_movements(tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    cases = [
        ({"id": "csd::neg", "activity_type": "CSD", "created_at": "2026-07-29T12:00:00Z", "net_amount": "-10"}, "negative net_amount"),
        ({"id": "csw::pos", "activity_type": "CSW", "created_at": "2026-07-29T12:00:00Z", "net_amount": "10"}, "positive net_amount"),
        ({"id": "csd::zero", "activity_type": "CSD", "created_at": "2026-07-29T12:00:00Z", "net_amount": "0"}, "zero net_amount"),
    ]
    for activity, match in cases:
        with pytest.raises(LedgerError, match=match):
            sync_broker_activities(store, [activity])
    assert ledger_balances(store)["cash"] == Decimal("1000")


def test_sync_broker_activities_still_refuses_deliberately_excluded_types(tmp_path):
    # INT, the DIV* variants, and JNLS stay fail-closed on purpose: each
    # needs its own reviewed accounting/tax treatment before ingestion.
    store, _ = _bootstrapped_store(tmp_path)
    for activity_type in ("INT", "DIVNRA", "DIVROC", "DIVCGL", "JNLC", "JNLS", "PTC"):
        activity = {
            "id": f"x::{activity_type}",
            "activity_type": activity_type,
            "created_at": "2026-07-29T12:00:00Z",
            "net_amount": "1.23",
        }
        with pytest.raises(LedgerError, match=f"unhandled activity type {activity_type}"):
            sync_broker_activities(store, [activity])
    assert ledger_balances(store)["cash"] == Decimal("1000")


def test_sync_broker_activities_one_bad_row_still_reports_and_posts_good_rows(tmp_path):
    # The dispatch collects per-row refusals instead of aborting mid-loop:
    # the good fee and dividend post (idempotently), and the final error
    # lists the bad row so the operator sees everything at once.
    store, _ = _bootstrapped_store(tmp_path)
    good_fee = _fee_activity()
    good_div = _div_activity()
    bad = _div_activity(activity_id="div::bad", net_amount="-1")
    bad["id"] = "div::bad"
    with pytest.raises(LedgerError, match="non-positive net_amount"):
        sync_broker_activities(store, [good_fee, good_div, bad])
    assert ledger_balances(store)["cash"] == Decimal("1037.04")


def test_sync_broker_activities_restores_reconciliation_after_dividend(tmp_path):
    # Miniature of the 2026-09-10 scenario: the broker credits the AEP
    # dividend; before the sync the books mismatch by the full amount,
    # after it they match exactly.
    store, _ = _bootstrapped_store(tmp_path, cash=1000.0)
    broker_now = _snapshot(cash=1037.05)
    before = reconcile_snapshot(store, broker_now)
    assert before["matched"] is False
    report = sync_broker_activities(store, [_div_activity()])
    assert report["inserted"] == 1
    after = reconcile_snapshot(store, broker_now)
    assert after["matched"] is True


def test_sync_broker_activities_uses_the_economic_date_for_dividends(tmp_path):
    """Creation time is a fetch boundary, not the dividend's tax/accounting date."""
    store, boot_at = _bootstrapped_store(tmp_path)
    dividend = _div_activity(
        created_at=None,
        date="2026-12-31",
        id="20270101010000000::year-boundary-div",
    )
    dividend.pop("created_at")

    sync_broker_activities(store, [dividend], created_after=boot_at)

    transaction = store.get_journal_transaction_by_external_id(
        "dividend:20270101010000000::year-boundary-div"
    )
    # 05:00Z during EST -- market-local midnight, not UTC midnight.
    assert transaction["occurred_at"] == "2026-12-31T05:00:00+00:00"
    assert _market_local_date(transaction["occurred_at"]) == "2026-12-31"


def test_sync_broker_activities_uses_the_economic_date_for_cash_flows(tmp_path):
    """A deposit must land in its real return interval, not at bootstrap."""
    store, boot_at = _bootstrapped_store(tmp_path)
    deposit = {
        "id": "20270101010000000::year-boundary-deposit",
        "activity_type": "CSD",
        "date": "2026-12-31",
        "net_amount": "500",
    }

    sync_broker_activities(store, [deposit], created_after=boot_at)

    transaction = store.get_journal_transaction_by_external_id(
        "cash_transfer:20270101010000000::year-boundary-deposit"
    )
    assert transaction["occurred_at"] == "2026-12-31T05:00:00+00:00"
    assert _market_local_date(transaction["occurred_at"]) == "2026-12-31"


@pytest.mark.parametrize("subtype_field", ["activity_sub_type", "activity_subtype"])
@pytest.mark.parametrize("subtype", ["SDIV", "SPD"])
def test_sync_broker_activities_refuses_non_cash_dividend_subtypes(
    tmp_path, subtype_field, subtype
):
    """Stock dividends and substitute payments need different accounting."""
    store, _ = _bootstrapped_store(tmp_path)
    activity = _div_activity()
    activity[subtype_field] = subtype
    with pytest.raises(LedgerError, match="unsupported DIV subtype"):
        sync_broker_activities(store, [activity])
    assert ledger_balances(store)["cash"] == Decimal("1000")


def test_sync_broker_activities_accepts_an_explicit_cash_dividend_subtype(tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    report = sync_broker_activities(
        store, [_div_activity(activity_subtype="CDIV")]
    )
    assert report["inserted"] == 1
    assert ledger_balances(store)["cash"] == Decimal("1037.05")


def test_sync_broker_activities_refuses_generic_cash_journals(tmp_path):
    """JNLC identifies cash, but not whether it is contributed capital."""
    store, _ = _bootstrapped_store(tmp_path)
    journal = {
        "id": "jnlc::broker-adjustment",
        "activity_type": "JNLC",
        "created_at": "2026-07-29T12:00:00Z",
        "net_amount": "4.81",
        "description": "Broker cash adjustment",
    }
    with pytest.raises(LedgerError, match="unhandled activity type JNLC"):
        sync_broker_activities(store, [journal])
    assert ledger_balances(store)["cash"] == Decimal("1000")


@pytest.mark.parametrize("activity", [
    _div_activity(currency="EUR"),
    {
        "id": "csd::eur",
        "activity_type": "CSD",
        "created_at": "2026-07-29T12:00:00Z",
        "net_amount": "10",
        "currency": "EUR",
    },
])
def test_sync_broker_activities_refuses_non_usd_money(activity, tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    with pytest.raises(LedgerError, match="currency"):
        sync_broker_activities(store, [activity])
    assert ledger_balances(store)["cash"] == Decimal("1000")


def test_sync_broker_activities_rejects_cross_type_broker_id_reuse(tmp_path):
    """One immutable broker activity ID may produce exactly one journal event."""
    store, _ = _bootstrapped_store(tmp_path)
    shared_id = "20260729113000000::shared-broker-id"
    sync_broker_activities(store, [_fee_activity(activity_id=shared_id)])

    with pytest.raises(LedgerError, match="already journaled as FEE"):
        sync_broker_activities(
            store, [_div_activity(id=shared_id)]
        )

    assert ledger_balances(store)["cash"] == Decimal("999.99")


def test_sync_broker_activities_preflights_cross_type_ids_before_posting(tmp_path):
    """A contradictory response must not persist whichever row appeared first."""
    store, _ = _bootstrapped_store(tmp_path)
    shared_id = "20260729113000000::same-response-id"
    fee = _fee_activity(activity_id=shared_id)
    dividend = _div_activity(id=shared_id)

    with pytest.raises(LedgerError, match="conflicting activity types"):
        sync_broker_activities(store, [fee, dividend])

    assert ledger_balances(store)["cash"] == Decimal("1000")


# --- Counter-review corrections DHCR-001/002 (2026-08-10) ---------------
# The review correctly replaced fetch timestamps with the provider's
# economic date, but stamped that date at UTC midnight -- which is the
# PREVIOUS evening in New York. Every consumer of these rows buckets in
# market-local time, so UTC midnight lands on the wrong side of two
# boundaries. These tests pin the corrected semantics through the real
# consumers rather than through a literal alone.


def _market_local_date(occurred_at):
    """The calendar day an occurred_at stamp falls on in the market's zone."""
    return (
        datetime.fromisoformat(str(occurred_at))
        .astimezone(MARKET_TIMEZONE)
        .date()
        .isoformat()
    )


@pytest.mark.parametrize(
    "activity_date, expected_utc",
    [
        ("2026-08-12", "2026-08-12T04:00:00+00:00"),  # EDT, UTC-4
        ("2026-12-15", "2026-12-15T05:00:00+00:00"),  # EST, UTC-5
    ],
)
def test_activity_dates_are_stamped_at_market_local_midnight(
    tmp_path, activity_date, expected_utc
):
    """Both sides of the DST boundary land on the right market-local day."""
    store, boot_at = _bootstrapped_store(tmp_path)
    deposit = {
        "id": f"csd::{activity_date}",
        "activity_type": "CSD",
        "created_at": f"{activity_date}T23:00:00Z",
        "date": activity_date,
        "net_amount": "500",
    }
    sync_broker_activities(store, [deposit], created_after=boot_at)
    transaction = store.get_journal_transaction_by_external_id(
        f"cash_transfer:csd::{activity_date}"
    )
    assert transaction["occurred_at"] == expected_utc
    assert _market_local_date(transaction["occurred_at"]) == activity_date


def test_a_winter_deposit_lands_in_its_own_session_return_interval(tmp_path):
    """DHCR-001: the external-flow window is bounded by real capture instants.

    `paper_evidence._net_external_flow` sums transfers in
    (previous capture, this capture]. The scheduled capture is 16:30
    Pacific, which under US STANDARD time is 00:30Z the following calendar
    day. A deposit stamped at UTC midnight therefore falls 30 minutes
    BEFORE the prior session's capture and is counted in that session's
    return interval instead of its own -- the deposit-as-return hazard
    GR-7c already had to close once. Market-local midnight is inside the
    correct window year-round.
    """
    from zoneinfo import ZoneInfo

    from assistant.paper_evidence import _net_external_flow

    pacific = ZoneInfo("America/Los_Angeles")

    def capture(day):  # the scheduled post-close capture instant
        return datetime.combine(
            day, datetime.min.time(), pacific
        ).replace(hour=16, minute=30).astimezone(timezone.utc)

    session = date(2026, 12, 15)
    previous_session = date(2026, 12, 14)

    store, boot_at = _bootstrapped_store(tmp_path)
    sync_broker_activities(
        store,
        [
            {
                "id": "csd::winter-deposit",
                "activity_type": "CSD",
                "created_at": "2026-12-15T14:00:00Z",
                "date": session.isoformat(),
                "net_amount": "500",
            }
        ],
        created_after=boot_at,
    )

    own_interval = _net_external_flow(
        store, after=capture(previous_session), through=capture(session)
    )
    previous_interval = _net_external_flow(
        store,
        after=capture(date(2026, 12, 11)),
        through=capture(previous_session),
    )
    assert own_interval == Decimal("500")
    assert previous_interval == Decimal("0")


def test_a_new_year_dividend_is_bucketed_into_the_correct_tax_year(tmp_path):
    """DHCR-001: `tax_year_of` converts to market time before taking .year.

    A 2027-01-01 activity stamped at UTC midnight reads as 2026-12-31
    19:00 in New York and buckets into tax year 2026 -- exactly the
    hazard `assistant/tax_reporting.py`'s own docstring warns about.
    Dividend income does not reach that report today; this pins the
    timestamp so it stays correct when it does.
    """
    from assistant.tax_reporting import tax_year_of

    store, boot_at = _bootstrapped_store(tmp_path)
    sync_broker_activities(
        store,
        [_div_activity(id="div::new-year", date="2027-01-01", created_at="2027-01-02T00:06:00Z")],
        created_after=boot_at,
    )
    transaction = store.get_journal_transaction_by_external_id(
        "dividend:div::new-year"
    )
    occurred = datetime.fromisoformat(transaction["occurred_at"])
    assert tax_year_of(occurred) == 2027
    assert _market_local_date(occurred) == "2027-01-01"


def test_the_ledger_and_tax_modules_share_one_market_timezone():
    """FCS-016: the zone that stamps a date must be the zone that buckets it."""
    from assistant.tax_reporting import TAX_YEAR_TIMEZONE

    assert MARKET_TIMEZONE is TAX_YEAR_TIMEZONE


def test_every_handled_activity_type_declares_an_external_id_prefix(tmp_path):
    """DHCR-002: a handled type with no prefix would raise KeyError.

    KeyError is not a LedgerError, so it escapes the per-row refusal
    handler as an unhandled crash instead of a clean fail-closed refusal.
    Deriving the handled set from the prefix map makes the drift
    impossible; this pins that relationship.
    """
    assert set(_ACTIVITY_EXTERNAL_ID_PREFIXES) == set(_HANDLED_ACTIVITY_TYPES)
    store = AssistantStore(tmp_path / "assistant.db")
    for activity_type in _HANDLED_ACTIVITY_TYPES:
        # Must not raise KeyError for any type the loop will accept.
        _assert_broker_activity_id_not_retyped(
            store, activity_type=activity_type, activity_id="probe"
        )


def test_an_undeclared_handled_type_refuses_cleanly_instead_of_crashing(tmp_path):
    """A future type added to the handled set without a prefix fails closed."""
    store = AssistantStore(tmp_path / "assistant.db")
    with pytest.raises(LedgerError, match="no external-id prefix is declared"):
        _assert_broker_activity_id_not_retyped(
            store, activity_type="INT", activity_id="probe"
        )


# --- Operator acknowledgement path (CR-W2 follow-up, 2026-08-11) ---------
# Before this, an unsupported broker activity blocked evidence capture until
# someone DEPLOYED new code -- and deploying closes the epoch, so one surprise
# activity type cost the entire accumulated run. This converts that into a
# single explicit human decision. Nothing is classified automatically: the
# operator picks the treatment, and every amount still comes from the broker.


def _unsupported_activity(**overrides):
    activity = {
        "id": "20260910000000000::div-variant",
        "activity_type": "DIVNRA",
        "created_at": "2026-07-29T11:30:00Z",
        "date": "2026-07-29",
        "net_amount": "31.50",
        "symbol": "AEP",
        "description": "Dividend net of withholding",
    }
    activity.update(overrides)
    return activity


def test_an_unsupported_activity_still_refuses_without_an_acknowledgement(tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    with pytest.raises(LedgerError, match="unhandled activity type DIVNRA"):
        sync_broker_activities(store, [_unsupported_activity()])
    assert ledger_balances(store)["cash"] == Decimal("1000")


def test_acknowledging_an_activity_lets_the_sync_journal_it(tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    activity = _unsupported_activity()
    result = acknowledge_broker_activity(
        store,
        activity,
        treatment="dividend",
        operator="sheltonchen",
        rationale="withholding variant; net cash is the dividend received",
        ticker="AEP",
    )
    assert result["inserted"] is True
    # Recording the decision must NOT journal anything by itself.
    assert ledger_balances(store)["cash"] == Decimal("1000")

    report = sync_broker_activities(store, [activity])
    assert report["inserted"] == 1
    assert report["by_acknowledged_treatment"] == {
        "dividend": {"inserted": 1, "duplicates": 0}
    }
    assert ledger_balances(store)["cash"] == Decimal("1031.50")
    replay = sync_broker_activities(store, [activity])
    assert replay["duplicates"] == 1
    assert ledger_balances(store)["cash"] == Decimal("1031.50")


def test_an_acknowledgement_does_not_apply_after_the_broker_row_changes(tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    acknowledge_broker_activity(
        store, _unsupported_activity(), treatment="dividend", operator="op",
        rationale="reviewed", ticker="AEP",
    )
    changed = _unsupported_activity(net_amount="9999.00")
    with pytest.raises(LedgerError, match="changed since it was"):
        sync_broker_activities(store, [changed])
    assert ledger_balances(store)["cash"] == Decimal("1000")


def test_no_cash_effect_cannot_be_used_to_wave_money_away(tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    with pytest.raises(LedgerError, match="only valid when the broker reports no cash"):
        acknowledge_broker_activity(
            store, _unsupported_activity(), treatment="no_cash_effect",
            operator="op", rationale="ignore it",
        )
    informational = _unsupported_activity(
        activity_type="NC", net_amount="0", id="nc::name-change"
    )
    acknowledge_broker_activity(
        store, informational, treatment="no_cash_effect",
        operator="op", rationale="name change, no cash movement",
    )
    report = sync_broker_activities(store, [informational])
    assert report["acknowledged_no_cash_effect"] == ["nc::name-change"]
    assert report["inserted"] == 0
    assert report["activities_seen"] == 1
    assert ledger_balances(store)["cash"] == Decimal("1000")


def test_the_operator_chooses_the_treatment_but_never_the_amount(tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    activity = _unsupported_activity(net_amount="31.50")
    acknowledge_broker_activity(
        store, activity, treatment="dividend", operator="op",
        rationale="reviewed", ticker="AEP",
    )
    stored = store.get_broker_activity_acknowledgement(activity["id"])
    assert "amount" not in stored["details"]
    assert "net_amount" not in stored["details"]
    sync_broker_activities(store, [activity])
    assert ledger_balances(store)["cash"] == Decimal("1031.50")


def test_acknowledgement_treatments_are_sign_checked_against_the_broker_row(tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    with pytest.raises(LedgerError, match="negative broker net_amount"):
        acknowledge_broker_activity(
            store, _unsupported_activity(), treatment="fee",
            operator="op", rationale="reviewed",
        )
    with pytest.raises(LedgerError, match="requires --ticker"):
        acknowledge_broker_activity(
            store, _unsupported_activity(), treatment="dividend",
            operator="op", rationale="reviewed",
        )
    with pytest.raises(LedgerError, match="positive broker net_amount"):
        acknowledge_broker_activity(
            store, _unsupported_activity(net_amount="-5"), treatment="dividend",
            operator="op", rationale="reviewed", ticker="AEP",
        )


def test_an_acknowledgement_requires_an_operator_and_a_rationale(tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    with pytest.raises(LedgerError, match="operator"):
        acknowledge_broker_activity(
            store, _unsupported_activity(), treatment="cash_transfer",
            operator="   ", rationale="reviewed",
        )
    with pytest.raises(LedgerError, match="written rationale"):
        acknowledge_broker_activity(
            store, _unsupported_activity(), treatment="cash_transfer",
            operator="op", rationale="",
        )
    with pytest.raises(LedgerError, match="unsupported treatment"):
        acknowledge_broker_activity(
            store, _unsupported_activity(), treatment="ignore",
            operator="op", rationale="reviewed",
        )


def test_an_acknowledgement_cannot_resurrect_pre_bootstrap_activity(tmp_path):
    """The bootstrap cutoff outranks an operator decision.

    A pre-bootstrap row is already inside opening cash; journaling it again
    would double-count. The acknowledgement is consulted only after that
    cutoff, so this must stay a skip, not an insert.
    """
    store, _ = _bootstrapped_store(tmp_path)
    old = _unsupported_activity(
        id="old::pre-bootstrap", created_at="2026-07-29T09:00:00Z"
    )
    acknowledge_broker_activity(
        store, old, treatment="dividend", operator="op",
        rationale="reviewed", ticker="AEP",
    )
    report = sync_broker_activities(store, [old])
    assert report["skipped_pre_bootstrap"] == 1
    assert report["inserted"] == 0
    assert ledger_balances(store)["cash"] == Decimal("1000")


def test_a_conflicting_second_acknowledgement_is_refused(tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    activity = _unsupported_activity()
    acknowledge_broker_activity(
        store, activity, treatment="dividend", operator="op",
        rationale="reviewed", ticker="AEP",
    )
    again = acknowledge_broker_activity(
        store, activity, treatment="dividend", operator="op",
        rationale="reviewed", ticker="AEP",
    )
    assert again["inserted"] is False
    with pytest.raises(BrokerActivityAcknowledgementConflictError):
        acknowledge_broker_activity(
            store, activity, treatment="cash_transfer", operator="op",
            rationale="changed my mind",
        )


def test_acknowledged_activity_restores_reconciliation(tmp_path):
    """The whole point: the epoch resumes without a deploy."""
    store, _ = _bootstrapped_store(tmp_path, cash=1000.0)
    activity = _unsupported_activity(net_amount="31.50")
    broker_now = _snapshot(cash=1031.50)
    assert reconcile_snapshot(store, broker_now)["matched"] is False
    acknowledge_broker_activity(
        store, activity, treatment="dividend", operator="op",
        rationale="reviewed", ticker="AEP",
    )
    sync_broker_activities(store, [activity])
    assert reconcile_snapshot(store, broker_now)["matched"] is True


def test_acknowledgement_table_migrates_onto_a_pre_migration_database(tmp_path):
    """CLAUDE.md 7: migrations must be idempotent and backward-compatible.

    Simulates a database created before this feature by dropping the table
    and re-opening with current code. Re-opening must recreate it WITHOUT
    disturbing existing rows -- the operator database is the live epoch's,
    so a migration that rebuilt anything would be unacceptable.
    """
    path = tmp_path / "assistant.db"
    store, _ = _bootstrapped_store(tmp_path)
    balances_before = ledger_balances(store)["cash"]

    with store._connect() as connection:
        connection.execute("DROP TABLE broker_activity_acknowledgements")
        remaining = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND "
            "name='broker_activity_acknowledgements'"
        ).fetchone()
    assert remaining is None, "precondition: the table is absent"

    reopened = AssistantStore(path)
    with reopened._connect() as connection:
        recreated = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND "
            "name='broker_activity_acknowledgements'"
        ).fetchone()
    assert recreated is not None, "re-opening must recreate the table"
    # Pre-existing journal rows are untouched by the migration.
    assert ledger_balances(reopened)["cash"] == balances_before
    assert reopened.list_broker_activity_acknowledgements() == []

    # And opening a third time is a no-op rather than an error.
    again = AssistantStore(path)
    assert again.list_broker_activity_acknowledgements() == []


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"status": "pending"}, "not executed"),
        ({"currency": "EUR"}, "currency is EUR"),
    ],
)
def test_acknowledgement_cannot_bypass_settlement_or_currency_guards(
    tmp_path, overrides, message
):
    """Human classification cannot turn an unsettled/non-USD row into USD cash."""
    store, _ = _bootstrapped_store(tmp_path)
    with pytest.raises(LedgerError, match=message):
        acknowledge_broker_activity(
            store,
            _unsupported_activity(**overrides),
            treatment="cash_transfer",
            operator="op",
            rationale="reviewed",
        )
    assert store.list_broker_activity_acknowledgements() == []
    assert ledger_balances(store)["cash"] == Decimal("1000")


def test_no_cash_effect_requires_an_explicit_zero_amount(tmp_path):
    """Missing is unknown, not broker evidence of a zero cash effect."""
    store, _ = _bootstrapped_store(tmp_path)
    activity = _unsupported_activity()
    activity.pop("net_amount")
    with pytest.raises(LedgerError, match="explicit zero"):
        acknowledge_broker_activity(
            store,
            activity,
            treatment="no_cash_effect",
            operator="op",
            rationale="reviewed",
        )


def test_acknowledgement_cannot_retype_an_already_journaled_activity_id(tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    shared_id = "shared::broker-activity"
    sync_broker_activities(store, [_fee_activity(activity_id=shared_id)])
    changed = _unsupported_activity(id=shared_id, net_amount="5.00")
    with pytest.raises(LedgerError, match="already journaled as FEE"):
        acknowledge_broker_activity(
            store,
            changed,
            treatment="cash_transfer",
            operator="op",
            rationale="broker changed the row type",
        )
    assert store.list_broker_activity_acknowledgements() == []
    assert ledger_balances(store)["cash"] == Decimal("999.99")


def test_idempotent_acknowledgement_includes_operator_and_rationale(tmp_path):
    """A different human or rationale is a different durable decision."""
    store, _ = _bootstrapped_store(tmp_path)
    activity = _unsupported_activity()
    acknowledge_broker_activity(
        store,
        activity,
        treatment="dividend",
        operator="first operator",
        rationale="first reason",
        ticker="AEP",
    )
    with pytest.raises(BrokerActivityAcknowledgementConflictError):
        acknowledge_broker_activity(
            store,
            activity,
            treatment="dividend",
            operator="second operator",
            rationale="second reason",
            ticker="AEP",
        )
    stored = store.get_broker_activity_acknowledgement(activity["id"])
    assert stored["operator"] == "first operator"
    assert stored["rationale"] == "first reason"


def test_acknowledgement_timestamp_must_be_timezone_aware(tmp_path):
    store, _ = _bootstrapped_store(tmp_path)
    with pytest.raises(LedgerError, match="timezone"):
        acknowledge_broker_activity(
            store,
            _unsupported_activity(),
            treatment="dividend",
            operator="op",
            rationale="reviewed",
            ticker="AEP",
            now=datetime(2026, 8, 11, 12, 0),
        )


def _fractional_exact_fill(boot_at):
    exact_qty = "0.123456789012345678"
    exact_price = "412.335000000000000001"
    return {
        "ticker": "AAPL",
        "side": "buy",
        "qty": float(exact_qty),
        "price": float(exact_price),
        "qty_decimal": exact_qty,
        "price_decimal": exact_price,
        "at": (boot_at + timedelta(hours=1)).isoformat(),
        "fill_id": "f-exact",
        "order_id": "o-exact",
        "proposal_id": "p-exact",
    }


def test_exact_fill_sync_is_idempotent_and_preserves_provider_digits(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    boot_at = datetime(2026, 1, 5, 14, tzinfo=timezone.utc)
    bootstrap_opening_snapshot(store, _snapshot(), confirmation="bootstrap", now=boot_at)
    fill = _fractional_exact_fill(boot_at)
    store.list_fills = lambda: [fill]

    assert sync_app_fills(store)["inserted"] == 1
    assert sync_app_fills(store)["duplicates"] == 1

    transaction = store.get_journal_transaction_by_external_id("app_fill:f-exact")
    assert transaction["metadata"]["qty"] == fill["qty_decimal"]
    assert transaction["metadata"]["price"] == fill["price_decimal"]
    assert fill["qty_decimal"] in transaction["description"]
    assert fill["price_decimal"] in transaction["description"]
    balances = ledger_balances(store)
    exact_gross = Decimal(fill["qty_decimal"]) * Decimal(fill["price_decimal"])
    assert balances["cash"] == Decimal("1000") - exact_gross


def test_legacy_float_fill_remains_idempotent_when_exact_companions_appear(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    boot_at = datetime(2026, 1, 5, 14, tzinfo=timezone.utc)
    bootstrap_opening_snapshot(store, _snapshot(), confirmation="bootstrap", now=boot_at)
    exact_fill = _fractional_exact_fill(boot_at)
    legacy_fill = {
        key: value for key, value in exact_fill.items() if not key.endswith("_decimal")
    }
    store.list_fills = lambda: [legacy_fill]
    assert sync_app_fills(store)["inserted"] == 1
    stored = store.get_journal_transaction_by_external_id("app_fill:f-exact")

    store.list_fills = lambda: [exact_fill]
    assert sync_app_fills(store)["duplicates"] == 1
    assert store.get_journal_transaction_by_external_id("app_fill:f-exact") == stored


def test_exact_fill_companion_change_is_still_a_content_conflict(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    boot_at = datetime(2026, 1, 5, 14, tzinfo=timezone.utc)
    bootstrap_opening_snapshot(store, _snapshot(), confirmation="bootstrap", now=boot_at)
    fill = _fractional_exact_fill(boot_at)
    store.list_fills = lambda: [fill]
    assert sync_app_fills(store)["inserted"] == 1

    changed = dict(fill, qty_decimal="0.123456789012345679")
    store.list_fills = lambda: [changed]
    with pytest.raises(LedgerError, match="different content"):
        sync_app_fills(store)
