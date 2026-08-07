"""
Readiness must agree with what storage.reserve_execution_budget() actually
enforces.

That function refuses when `existing_count + 1 > max_daily_orders` and when
`existing_notional + notional > max_daily_notional`, and it separately rejects
`notional <= 0`. So another order fits only when the count is STRICTLY below
its cap, and -- because the smallest possible next order still has positive
notional -- only when the notional is strictly below its cap too. Readiness
previously used `<=` on both, reporting ready=True at 1/1 orders and a
fully-consumed notional budget while submission would have been refused
(GPT review, 2026-07-29).
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

from assistant.policy import TradingPolicy
from assistant.readiness import transaction_readiness
from assistant.storage import AssistantStore

_NOW = datetime(2026, 7, 29, 15, 0, tzinfo=timezone.utc)


def _ready_store(temp: str) -> AssistantStore:
    store = AssistantStore(Path(temp) / "assistant.db")
    store.set_system_state(
        "last_order_reconciliation",
        {"at": _NOW.isoformat(), "checked": 0, "updated": 0, "error_count": 0},
    )
    return store


def _policy(max_orders: int = 3, max_notional: float = 10_000.0) -> TradingPolicy:
    return TradingPolicy(
        version="test",
        name="test",
        execution_mode="paper",
        max_daily_order_count=max_orders,
        max_daily_submitted_notional=max_notional,
    )


def _budget_check(store: AssistantStore, policy: TradingPolicy) -> dict:
    report = transaction_readiness(store, policy, now=_NOW, check_broker=False)
    return next(c for c in report["checks"] if c["name"] == "daily_submission_budget")


def _consume(store: AssistantStore, *, orders: int, notional_each: float, policy: TradingPolicy):
    """Reserve real budget through the authoritative code path, so these tests
    cannot drift from reserve_execution_budget()'s own accounting."""
    trading_day = _NOW.astimezone().date().isoformat()
    usage_day = store.get_execution_budget_usage(trading_day)
    del usage_day
    for index in range(orders):
        proposal_id = f"tp-{index}"
        store.save_proposal(
            {
                "proposal_id": proposal_id,
                "created_at": _NOW.isoformat(),
                "expires_at": "2026-07-30T15:00:00+00:00",
                "status": "filled",
                "idempotency_key": f"idem-{proposal_id}",
                "intent": {
                    "ticker": f"T{index}",
                    "side": "buy",
                    "shares": 1,
                    "order_type": "market",
                    "limit_price": None,
                },
            }
        )
        store.reserve_execution_budget(
            proposal_id,
            trading_day=trading_day,
            notional=notional_each,
            max_daily_notional=policy.max_daily_submitted_notional,
            max_daily_orders=policy.max_daily_order_count,
        )


def test_order_count_below_the_cap_is_ready():
    with tempfile.TemporaryDirectory() as temp:
        store = _ready_store(temp)
        policy = _policy(max_orders=2, max_notional=10_000.0)
        _consume(store, orders=1, notional_each=100.0, policy=policy)
        assert _budget_check(store, policy)["ok"] is True


def test_order_count_exactly_at_the_cap_is_not_ready():
    with tempfile.TemporaryDirectory() as temp:
        store = _ready_store(temp)
        policy = _policy(max_orders=1, max_notional=10_000.0)
        _consume(store, orders=1, notional_each=100.0, policy=policy)
        check = _budget_check(store, policy)
        assert check["ok"] is False, (
            "1 of 1 allowed orders leaves no room for another submission"
        )
        assert "room for 0 more" in check["detail"]
        report = transaction_readiness(store, policy, now=_NOW, check_broker=False)
        assert report["ready"] is False


def test_notional_below_the_cap_is_ready():
    with tempfile.TemporaryDirectory() as temp:
        store = _ready_store(temp)
        policy = _policy(max_orders=5, max_notional=1_000.0)
        _consume(store, orders=1, notional_each=900.0, policy=policy)
        assert _budget_check(store, policy)["ok"] is True


def test_notional_exactly_at_the_cap_is_not_ready():
    """reserve_execution_budget() rejects notional <= 0, so the smallest
    possible next order still needs strictly positive headroom."""
    with tempfile.TemporaryDirectory() as temp:
        store = _ready_store(temp)
        policy = _policy(max_orders=5, max_notional=1_000.0)
        _consume(store, orders=1, notional_each=1_000.0, policy=policy)
        check = _budget_check(store, policy)
        assert check["ok"] is False
        assert "$0.00 remaining" in check["detail"], check["detail"]


def test_one_budget_exhausted_while_the_other_has_room_is_not_ready():
    with tempfile.TemporaryDirectory() as temp:
        store = _ready_store(temp)
        # Notional exhausted, order count still available.
        policy = _policy(max_orders=5, max_notional=1_000.0)
        _consume(store, orders=1, notional_each=1_000.0, policy=policy)
        assert _budget_check(store, policy)["ok"] is False

    with tempfile.TemporaryDirectory() as temp:
        store = _ready_store(temp)
        # Order count exhausted, notional still available.
        policy = _policy(max_orders=1, max_notional=10_000.0)
        _consume(store, orders=1, notional_each=10.0, policy=policy)
        assert _budget_check(store, policy)["ok"] is False


def test_readiness_agrees_with_reserve_execution_budget_at_the_boundary():
    """The property that matters: readiness must never claim capacity that the
    authoritative reservation call would then refuse."""
    with tempfile.TemporaryDirectory() as temp:
        store = _ready_store(temp)
        policy = _policy(max_orders=2, max_notional=1_000.0)
        _consume(store, orders=2, notional_each=100.0, policy=policy)

        readiness_says_ok = _budget_check(store, policy)["ok"]
        trading_day = _NOW.astimezone().date().isoformat()
        store.save_proposal(
            {
                "proposal_id": "tp-next",
                "created_at": _NOW.isoformat(),
                "expires_at": "2026-07-30T15:00:00+00:00",
                "status": "filled",
                "idempotency_key": "idem-tp-next",
                "intent": {
                    "ticker": "NEXT",
                    "side": "buy",
                    "shares": 1,
                    "order_type": "market",
                    "limit_price": None,
                },
            }
        )
        try:
            store.reserve_execution_budget(
                "tp-next",
                trading_day=trading_day,
                notional=1.0,
                max_daily_notional=policy.max_daily_submitted_notional,
                max_daily_orders=policy.max_daily_order_count,
            )
            reservation_succeeded = True
        except ValueError:
            reservation_succeeded = False

        assert readiness_says_ok == reservation_succeeded, (
            f"readiness reported ok={readiness_says_ok} but reserving actually "
            f"{'succeeded' if reservation_succeeded else 'failed'}"
        )
        assert reservation_succeeded is False


if __name__ == "__main__":
    test_order_count_below_the_cap_is_ready()
    test_order_count_exactly_at_the_cap_is_not_ready()
    test_notional_below_the_cap_is_ready()
    test_notional_exactly_at_the_cap_is_not_ready()
    test_one_budget_exhausted_while_the_other_has_room_is_not_ready()
    test_readiness_agrees_with_reserve_execution_budget_at_the_boundary()
    print("All readiness-budget tests passed.")
