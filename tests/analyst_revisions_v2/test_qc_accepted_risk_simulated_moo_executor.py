import dataclasses
from datetime import datetime
from decimal import Decimal
from enum import IntEnum

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_simulated_moo_executor as subject,
)


class OrderStatus(IntEnum):
    NEW = 0
    SUBMITTED = 1
    PARTIALLY_FILLED = 2
    FILLED = 3
    CANCELED = 5
    NONE = 6
    INVALID = 7
    CANCEL_PENDING = 8
    UPDATE_SUBMITTED = 9


class BadCanceledStatus(IntEnum):
    NEW = 0
    SUBMITTED = 1
    PARTIALLY_FILLED = 2
    FILLED = 3
    CANCELED = 4
    NONE = 6
    INVALID = 7
    CANCEL_PENDING = 8
    UPDATE_SUBMITTED = 9


@dataclasses.dataclass
class _Ticket:
    order_id: int


@dataclasses.dataclass
class _CashAmount:
    amount: Decimal
    currency: str = "USD"


@dataclasses.dataclass
class _OrderFee:
    value: _CashAmount


@dataclasses.dataclass
class _Event:
    order_id: int
    id: int
    status: OrderStatus
    fill_quantity: Decimal = Decimal(0)
    fill_price: Decimal = Decimal(0)
    order_fee: _OrderFee = dataclasses.field(
        default_factory=lambda: _OrderFee(_CashAmount(Decimal(0)))
    )


class _Harness:
    def __init__(
        self,
        *,
        quantities=None,
        cash=Decimal("1000"),
        synchronous=True,
        external=None,
    ):
        self.quantities = dict(quantities or {})
        self.cash = cash
        self.synchronous = synchronous
        self.external = external
        self.executor = None
        self.submissions = []
        self.next_order_id = 100
        self.next_event_id = 1
        self.fill_prices = {
            "OLD": Decimal("10"),
            "NEW": Decimal("20"),
            "A": Decimal("10"),
        }

    def security_for_id(self, security_id):
        return "symbol:" + security_id

    def current_quantity(self, security_id):
        return self.quantities.get(security_id, 0)

    def current_holding_census(self):
        return dict(self.quantities)

    def current_cash(self):
        return self.cash

    def submit(self, symbol, signed_quantity, tag):
        security_id = symbol.split(":", 1)[1]
        order_id = self.next_order_id
        self.next_order_id += 1
        self.submissions.append((security_id, signed_quantity, tag, order_id))
        if self.synchronous:
            price = self.fill_prices[security_id]
            fee = price * Decimal(abs(signed_quantity)) * Decimal("0.001")
            event = _Event(
                order_id=order_id,
                id=self.next_event_id,
                status=OrderStatus.FILLED,
                fill_quantity=Decimal(signed_quantity),
                fill_price=price,
                order_fee=_OrderFee(_CashAmount(fee)),
            )
            self.next_event_id += 1
            self.executor.on_order_event(event)
            if signed_quantity < 0:
                self.quantities[security_id] += signed_quantity
                if self.quantities[security_id] == 0:
                    del self.quantities[security_id]
                self.cash += price * Decimal(-signed_quantity) - fee
            else:
                self.quantities[security_id] = (
                    self.quantities.get(security_id, 0) + signed_quantity
                )
                self.cash -= price * Decimal(signed_quantity) + fee
        return _Ticket(order_id)

    def build(self, *, live_mode=False, status_enum=OrderStatus):
        self.live_mode = live_mode
        self.executor = subject.SimulatedMooExecutor(
            current_live_mode=lambda: self.live_mode,
            order_status_enum=status_enum,
            order_status_to_int=int,
            security_for_id=self.security_for_id,
            current_quantity=self.current_quantity,
            current_holding_census=self.current_holding_census,
            current_cash=self.current_cash,
            submit_market_on_open=self.submit,
            external_order_event_handler=self.external,
            holding_drift_replan=getattr(self, "holding_drift_replan", None),
        )
        return self.executor


def _prepare_rotation(executor):
    return executor.prepare_rebalance(
        decision_session="2025-01-02",
        execution_session="2025-01-03",
        target_weights={"NEW": Decimal("0.98")},
        reference_prices={
            "NEW": Decimal("20"),
            "OLD": Decimal("10"),
        },
    )


def _preopen():
    return datetime(2025, 1, 3, 9, 20)


@pytest.mark.parametrize("live_mode", [True, 0, None])
def test_executor_refuses_live_or_non_boolean_mode(live_mode):
    harness = _Harness()
    with pytest.raises(subject.SimulatedMooExecutorError):
        harness.build(live_mode=live_mode)


def test_executor_rechecks_live_mode_immediately_before_submission():
    harness = _Harness(quantities={"OLD": 10}, cash=Decimal("900"))
    executor = harness.build()
    _prepare_rotation(executor)
    harness.live_mode = True

    with pytest.raises(subject.SimulatedMooExecutorError):
        executor.on_preopen(_preopen())

    assert harness.submissions == []


def test_reflected_status_map_pins_canceled_to_numeric_five():
    harness = _Harness()
    with pytest.raises(
        subject.SimulatedMooExecutorError,
        match="reflected OrderStatus map changed",
    ):
        harness.build(status_enum=BadCanceledStatus)


def test_rotation_submits_whole_share_sells_before_buys_and_summarizes():
    harness = _Harness(quantities={"OLD": 10}, cash=Decimal("900"))
    executor = harness.build()
    plan = _prepare_rotation(executor)

    assert [item.side for item in plan.intents] == ["SELL", "BUY"]
    assert executor.lifecycle_state() == {
        "schema": subject.STATE_SCHEMA,
        "terminal": False,
        "decision_count": 1,
        "submitted_rebalance_count": 0,
        "completed_rebalance_count": 0,
        "holding_drift_skipped_rebalance_count": 0,
        "submitted_order_count": 0,
        "pending_execution_session": "2025-01-03",
        "open_rebalance": False,
        "external_order_event_count": 0,
    }
    assert executor.on_preopen(_preopen()) == subject.PREOPEN_SUBMITTED
    assert [row[0] for row in harness.submissions] == ["OLD", "NEW"]
    assert [row[1] for row in harness.submissions] == [-10, 49]

    result = executor.terminal_aggregate()
    assert result["decision_count"] == 1
    assert result["completed_rebalance_count"] == 1
    assert result["submitted_order_count"] == 2
    assert result["filled_order_count_sum"] == 2
    assert result["canceled_order_count_sum"] == 0
    assert result["modeled_fee_amount"] == "1.08"
    assert result["actual_engine_fee_amount"] == "1.08"
    assert result["fee_mismatch"] is False
    assert result["execution_failure"] is False
    assert result["run_valid"] is True
    assert result["raw_order_rows_in_summary"] is False
    assert result["raw_security_rows_in_summary"] is False
    assert executor.terminal_aggregate() == result


def test_prepare_uses_explicit_reference_prices_and_rejects_incomplete_map():
    harness = _Harness(quantities={"OLD": 10}, cash=Decimal("900"))
    executor = harness.build()
    with pytest.raises(
        subject.SimulatedMooExecutorError,
        match="reference prices must be an exact dict over",
    ):
        executor.prepare_rebalance(
            decision_session="2025-01-02",
            execution_session="2025-01-03",
            target_weights={"NEW": Decimal("0.98")},
            reference_prices={"NEW": Decimal("20")},
        )


def test_next_session_preopen_clock_is_exact_and_early_call_is_inert():
    harness = _Harness()
    executor = harness.build()
    executor.prepare_rebalance(
        decision_session="2025-01-02",
        execution_session="2025-01-03",
        target_weights={"A": Decimal("0.98")},
        reference_prices={"A": Decimal("10")},
    )
    assert (
        executor.on_preopen(datetime(2025, 1, 2, 9, 20))
        == subject.PREOPEN_NOT_DUE
    )
    with pytest.raises(
        subject.SimulatedMooExecutorError,
        match="missed its exact next session",
    ):
        executor.on_preopen(datetime(2025, 1, 3, 9, 19))


@pytest.mark.parametrize("rogue_quantity", [Decimal("0.5"), -1])
def test_complete_holding_census_drift_is_a_counted_no_order_skip(
    rogue_quantity,
):
    harness = _Harness()
    executor = harness.build()
    executor.prepare_rebalance(
        decision_session="2025-01-02",
        execution_session="2025-01-03",
        target_weights={"A": Decimal("0.98")},
        reference_prices={"A": Decimal("10")},
    )
    harness.quantities["ROGUE"] = rogue_quantity

    assert executor.on_preopen(_preopen()) == subject.PREOPEN_DRIFT_SKIPPED
    assert harness.submissions == []
    result = executor.terminal_aggregate()
    assert result["holding_drift_skipped_rebalance_count"] == 1
    assert result["submitted_rebalance_count"] == 0
    assert result["completed_rebalance_count"] == 0
    assert result["corporate_action_replan_count"] == 0
    assert len(result["corporate_action_replan_path_sha256"]) == 64
    assert result["run_valid"] is False
    assert "ROGUE" not in str(result)


def test_authorized_split_like_holding_drift_replans_and_submits():
    harness = _Harness(quantities={"OLD": 10}, cash=Decimal("900"))
    callback_calls = []

    def replan(plan, observed_cash, observed_quantities, actual_time):
        callback_calls.append(
            (plan, observed_cash, observed_quantities, actual_time)
        )
        return {
            "reference_prices": {
                "NEW": Decimal("20"),
                "OLD": Decimal("5"),
            },
            "receipt_sha256": "a" * 64,
        }

    harness.holding_drift_replan = replan
    executor = harness.build()
    original = _prepare_rotation(executor)

    # Model a 2-for-1 split applied by the engine before the pre-open hook.
    harness.quantities["OLD"] = 20
    harness.fill_prices["OLD"] = Decimal("5")

    assert executor.on_preopen(_preopen()) == subject.PREOPEN_SUBMITTED
    assert len(callback_calls) == 1
    observed_plan, observed_cash, observed_quantities, observed_time = (
        callback_calls[0]
    )
    assert observed_plan == original
    assert observed_cash == Decimal("900")
    assert observed_quantities == {"OLD": 20}
    assert observed_time == _preopen()
    assert [row[0] for row in harness.submissions] == ["OLD", "NEW"]
    assert [row[1] for row in harness.submissions] == [-20, 49]

    result = executor.terminal_aggregate()
    assert result["holding_drift_skipped_rebalance_count"] == 0
    assert result["corporate_action_replan_count"] == 1
    assert len(result["corporate_action_replan_path_sha256"]) == 64
    assert result["submitted_rebalance_count"] == 1
    assert result["completed_rebalance_count"] == 1
    assert result["run_valid"] is True


@pytest.mark.parametrize(
    "callback_result",
    [
        {"reference_prices": {"A": Decimal("10")}},
        {
            "reference_prices": {"A": Decimal("10")},
            "receipt_sha256": "not-a-sha256",
        },
    ],
)
def test_holding_drift_replan_malformed_receipt_fails_closed(
    callback_result,
):
    harness = _Harness()
    harness.holding_drift_replan = lambda *_args: callback_result
    executor = harness.build()
    executor.prepare_rebalance(
        decision_session="2025-01-02",
        execution_session="2025-01-03",
        target_weights={"A": Decimal("0.98")},
        reference_prices={"A": Decimal("10")},
    )
    harness.quantities["ROGUE"] = 1

    with pytest.raises(
        subject.SimulatedMooExecutorError,
        match="holding-drift replan callback returned an invalid receipt",
    ):
        executor.on_preopen(_preopen())

    assert harness.submissions == []


def test_holding_drift_replan_none_is_an_explicit_counted_no_authority_skip():
    harness = _Harness()
    harness.holding_drift_replan = lambda *_args: None
    executor = harness.build()
    executor.prepare_rebalance(
        decision_session="2025-01-02",
        execution_session="2025-01-03",
        target_weights={"A": Decimal("0.98")},
        reference_prices={"A": Decimal("10")},
    )
    harness.quantities["ROGUE"] = 1

    assert executor.on_preopen(_preopen()) == subject.PREOPEN_DRIFT_SKIPPED
    assert harness.submissions == []
    assert executor.terminal_aggregate()[
        "holding_drift_skipped_rebalance_count"
    ] == 1


def test_quantity_callback_must_agree_with_complete_census():
    harness = _Harness(quantities={"A": 1})
    executor = harness.build()
    harness.current_quantity = lambda _security_id: 2
    executor._current_quantity = harness.current_quantity
    with pytest.raises(
        subject.SimulatedMooExecutorError,
        match="disagrees with complete holding census",
    ):
        executor.prepare_rebalance(
            decision_session="2025-01-02",
            execution_session="2025-01-03",
            target_weights={"A": Decimal("0.98")},
            reference_prices={"A": Decimal("10")},
        )


def test_cash_increase_replans_but_cash_decrease_refuses():
    increased = _Harness()
    executor = increased.build()
    original = executor.prepare_rebalance(
        decision_session="2025-01-02",
        execution_session="2025-01-03",
        target_weights={"A": Decimal("0.98")},
        reference_prices={"A": Decimal("10")},
    )
    increased.cash = Decimal("1010")
    assert executor.on_preopen(_preopen()) == subject.PREOPEN_SUBMITTED
    assert increased.submissions[0][1] == 98
    assert executor._open_plan.plan_sha256 != original.plan_sha256

    decreased = _Harness()
    executor = decreased.build()
    executor.prepare_rebalance(
        decision_session="2025-01-02",
        execution_session="2025-01-03",
        target_weights={"A": Decimal("0.98")},
        reference_prices={"A": Decimal("10")},
    )
    decreased.cash = Decimal("999")
    with pytest.raises(
        subject.SimulatedMooExecutorError,
        match="overnight cash decreased",
    ):
        executor.on_preopen(_preopen())


def test_canceled_five_is_lifecycle_failure_not_unsupported_status():
    harness = _Harness(synchronous=False)
    executor = harness.build()
    executor.prepare_rebalance(
        decision_session="2025-01-02",
        execution_session="2025-01-03",
        target_weights={"A": Decimal("0.98")},
        reference_prices={"A": Decimal("10")},
    )
    assert executor.on_preopen(_preopen()) == subject.PREOPEN_SUBMITTED
    order_id = harness.submissions[0][3]
    executor.on_order_event(_Event(
        order_id=order_id,
        id=1,
        status=OrderStatus.CANCELED,
    ))
    result = executor.terminal_aggregate()
    assert result["canceled_order_count_sum"] == 1
    assert result["execution_failure"] is True
    assert result["run_valid"] is False


def test_synchronous_event_must_match_returned_ticket():
    harness = _Harness(synchronous=False)
    executor = harness.build()

    def mismatched_submit(_symbol, quantity, _tag):
        executor.on_order_event(_Event(
            order_id=999,
            id=1,
            status=OrderStatus.FILLED,
            fill_quantity=Decimal(quantity),
            fill_price=Decimal("10"),
            order_fee=_OrderFee(_CashAmount(Decimal("0.98"))),
        ))
        return _Ticket(100)

    executor._submit_market_on_open = mismatched_submit
    executor.prepare_rebalance(
        decision_session="2025-01-02",
        execution_session="2025-01-03",
        target_weights={"A": Decimal("0.98")},
        reference_prices={"A": Decimal("10")},
    )
    with pytest.raises(
        subject.SimulatedMooExecutorError,
        match="synchronous event does not match returned MOO ticket",
    ):
        executor.on_preopen(_preopen())


def test_incomplete_order_lifecycle_refuses_terminal_aggregate():
    harness = _Harness(synchronous=False)
    executor = harness.build()
    executor.prepare_rebalance(
        decision_session="2025-01-02",
        execution_session="2025-01-03",
        target_weights={"A": Decimal("0.98")},
        reference_prices={"A": Decimal("10")},
    )
    executor.on_preopen(_preopen())
    with pytest.raises(
        subject.SimulatedMooExecutorError,
        match="every order must have a terminal status",
    ):
        executor.terminal_aggregate()


def test_unknown_event_requires_strict_external_receipt_hook():
    event = _Event(
        order_id=900,
        id=7,
        status=OrderStatus.FILLED,
        fill_quantity=Decimal(1),
        fill_price=Decimal("10"),
    )
    without = _Harness().build()
    with pytest.raises(
        subject.SimulatedMooExecutorError,
        match="no strict handler",
    ):
        without.on_order_event(event)

    calls = []

    def handler(observed, engine_order, status):
        calls.append((observed, engine_order, status))
        return "a" * 64

    harness = _Harness(external=handler)
    executor = harness.build()
    executor.on_order_event(event, engine_order="forced-order")
    assert calls == [(event, "forced-order", "Filled")]
    assert executor.lifecycle_state()["external_order_event_count"] == 1


def test_external_hook_refuses_non_hash_receipt():
    harness = _Harness(external=lambda *_args: True)
    executor = harness.build()
    with pytest.raises(
        subject.SimulatedMooExecutorError,
        match="no exact SHA-256 receipt",
    ):
        executor.on_order_event(_Event(
            order_id=900,
            id=7,
            status=OrderStatus.CANCELED,
        ))


def test_no_intent_rebalance_closes_without_order_submission():
    harness = _Harness(quantities={"A": 98}, cash=Decimal("20"))
    executor = harness.build()
    plan = executor.prepare_rebalance(
        decision_session="2025-01-02",
        execution_session="2025-01-03",
        target_weights={"A": Decimal("0.98")},
        reference_prices={"A": Decimal("10")},
    )
    assert plan.intents == ()
    assert executor.on_preopen(_preopen()) == subject.PREOPEN_SUBMITTED
    result = executor.terminal_aggregate()
    assert harness.submissions == []
    assert result["completed_rebalance_count"] == 1
    assert result["submitted_order_count"] == 0
    assert result["run_valid"] is True


def test_actions_after_terminal_refuse_but_terminal_read_is_idempotent():
    harness = _Harness(quantities={"A": 98}, cash=Decimal("20"))
    executor = harness.build()
    executor.prepare_rebalance(
        decision_session="2025-01-02",
        execution_session="2025-01-03",
        target_weights={"A": Decimal("0.98")},
        reference_prices={"A": Decimal("10")},
    )
    executor.on_preopen(_preopen())
    first = executor.terminal_aggregate()
    assert executor.terminal_aggregate() == first
    assert executor.lifecycle_state()["terminal"] is True
    with pytest.raises(
        subject.SimulatedMooExecutorError,
        match="already terminal",
    ):
        executor.prepare_rebalance(
            decision_session="2025-01-06",
            execution_session="2025-01-07",
            target_weights={"A": Decimal("0.98")},
            reference_prices={"A": Decimal("10")},
        )
