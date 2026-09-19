import dataclasses
import json
from datetime import datetime
from decimal import Decimal

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_order_level_core as core


@pytest.mark.parametrize(
    ("numeric", "name"),
    (
        ("0", "New"), ("1", "Submitted"), ("2", "PartiallyFilled"),
        ("3", "Filled"), ("5", "Canceled"), ("6", "None"),
        ("7", "Invalid"), ("8", "CancelPending"),
        ("9", "UpdateSubmitted"),
    ),
)
def test_documented_qc_numeric_order_status_spellings_are_exact(numeric, name):
    assert core.qc_order_status_text(numeric, numeric=True) == name
    assert core.qc_order_status_text(numeric, numeric=False) == numeric
    assert core.qc_order_status_text("OrderStatus." + name, numeric=True) == name


def _plan(
    *,
    rebalance_id="rebalance-2026-01-05",
    starting_cash=Decimal("2000"),
    current_quantities=None,
    reference_prices=None,
    target_weights=None,
):
    return core.plan_rebalance(
        rebalance_id=rebalance_id,
        starting_cash=starting_cash,
        current_quantities=(
            {"TICKER_ALPHA_RAW": 100}
            if current_quantities is None
            else current_quantities
        ),
        reference_prices=(
            {
                "TICKER_ALPHA_RAW": Decimal("100"),
                "TICKER_BETA_RAW": Decimal("50"),
            }
            if reference_prices is None
            else reference_prices
        ),
        target_weights=(
            {
                "TICKER_ALPHA_RAW": Decimal("0.49"),
                "TICKER_BETA_RAW": Decimal("0.49"),
            }
            if target_weights is None
            else target_weights
        ),
    )


def test_next_session_preopen_requires_exact_clock_and_unchanged_account():
    kwargs = {
        "expected": "2026-01-05",
        "actual_time": datetime.fromisoformat("2026-01-05T09:20:00"),
        "planned_cash": Decimal("200"),
        "observed_cash": Decimal("200"),
        "planned_quantities": {"stock": 1},
        "observed_quantities": {"stock": 1},
        "error_type": ValueError,
    }
    assert core.require_next_session_preopen(**kwargs) is None
    assert core.require_next_session_preopen(
        **{**kwargs, "actual_time": datetime.fromisoformat("2026-01-05T09:27:00")}
    ) is None
    for clock in ("2026-01-02T09:20:00", "2026-01-05T09:28:00"):
        with pytest.raises(ValueError, match="missed its exact next session"):
            core.require_next_session_preopen(
                **{**kwargs, "actual_time": datetime.fromisoformat(clock)}
            )
    for changed in (
        {"observed_cash": Decimal("199")},
        {"observed_quantities": {"stock": 2}},
    ):
        with pytest.raises(ValueError, match="overnight account changed"):
            core.require_next_session_preopen(**{**kwargs, **changed})


def test_aggregate_coverage_statistics_preserves_exact_proxy_decimal_census():
    rows = ({
        "resolved_member_count_ratio": "0.5",
        "resolved_constituent_weight_ratio": "0.86",
        "positive_constituent_weight_total": "1",
        "qqq_proxy_constituent_weight_ratio": "0.14",
        "positive_weight_member_count": 100,
        "resolved_positive_weight_member_count": 50,
    },)
    values, stats = core.coverage_statistics(rows, True)
    assert values["resolved_constituent_weight_ratio"] == (Decimal("0.86"),)
    assert stats == {
        "coverage_decision_count": 1,
        "positive_weight_member_count_sum": 100,
        "resolved_positive_weight_member_count_sum": 50,
        "mean_resolved_member_count_ratio": "0.5",
        "mean_resolved_constituent_weight_ratio": "0.86",
        "mean_positive_constituent_weight_total": "1",
        "mean_qqq_proxy_constituent_weight_ratio": "0.14",
        "minimum_resolved_member_count_ratio": "0.5",
        "minimum_resolved_constituent_weight_ratio": "0.86",
        "minimum_positive_constituent_weight_total": "1",
        "minimum_qqq_proxy_constituent_weight_ratio": "0.14",
    }
    _, legacy = core.coverage_statistics(rows, False)
    assert "mean_qqq_proxy_constituent_weight_ratio" not in legacy


def _sell(plan):
    return next(intent for intent in plan.intents if intent.side == core.SELL)


def _buy(plan):
    return next(intent for intent in plan.intents if intent.side == core.BUY)


def _event(
    intent,
    *,
    event_id,
    status=core.FILLED,
    quantity=None,
    price=None,
    rebalance_id=None,
    client_order_id=None,
    fee_amount=None,
    fee_currency="USD",
):
    fill_quantity = intent.quantity if quantity is None else quantity
    fill_price = intent.reference_price if price is None else price
    engine_fee_amount = (
        Decimal(fill_quantity) * fill_price * core.MODELED_FEE_RATE_PER_SIDE
        if fee_amount is None
        else fee_amount
    )
    return core.FillEvent(
        event_id=event_id,
        rebalance_id=(
            intent.rebalance_id if rebalance_id is None else rebalance_id
        ),
        client_order_id=(
            intent.client_order_id
            if client_order_id is None
            else client_order_id
        ),
        status=status,
        fill_quantity=fill_quantity,
        fill_price=fill_price,
        engine_fee_amount=engine_fee_amount,
        engine_fee_currency=fee_currency,
    )


def _terminal_events(plan):
    return tuple(
        _event(intent, event_id=f"event-{intent.ordinal}")
        for intent in plan.intents
    )


def test_lifecycle_census_preserves_fee_count_failure_and_digest():
    plan = _plan()
    record = core.summarize_order_lifecycle(
        plan, _terminal_events(plan)
    ).to_record()
    one = core.aggregate_lifecycle_records((record,), len(plan.intents))
    assert one["fee"] == Decimal(record["modeled_fee_amount"])
    assert one["actual_fee"] == Decimal(record["actual_engine_fee_amount"])
    assert one["filled"] == len(plan.intents)
    assert one["execution_failure"] is False
    assert one["fee_mismatch"] is False
    assert len(one["digest"]) == 64
    invalid = {**record, "invalid_order_count": 1}
    two = core.aggregate_lifecycle_records((invalid,), len(plan.intents))
    assert two["invalid"] == 1
    assert two["execution_failure"] is True
    assert two["digest"] != one["digest"]


def _assert_refusal(expected, function, *args, **kwargs):
    with pytest.raises(core.OrderLevelBacktestError, match=f"^{expected}$"):
        function(*args, **kwargs)


def test_planner_is_exact_whole_share_long_only_sell_first_and_deterministic():
    plan = _plan()
    retry = _plan()

    assert plan == retry
    assert plan.starting_equity == Decimal("12000")
    assert dict(plan.target_quantities) == {
        "TICKER_ALPHA_RAW": 58,
        "TICKER_BETA_RAW": 117,
    }
    assert [(item.side, item.security_id, item.quantity) for item in plan.intents] == [
        (core.SELL, "TICKER_ALPHA_RAW", 42),
        (core.BUY, "TICKER_BETA_RAW", 117),
    ]
    assert all(type(item.quantity) is int and item.quantity > 0 for item in plan.intents)
    assert sum(dict(plan.target_weights).values()) == Decimal("0.98")
    assert all(quantity >= 0 for _, quantity in plan.target_quantities)
    assert len(plan.plan_sha256) == 64


def test_intents_sort_every_sell_before_every_buy_then_by_security_id():
    plan = _plan(
        starting_cash=Decimal("1000"),
        current_quantities={"SELL_Z": 100, "SELL_A": 100},
        reference_prices={
            "SELL_Z": Decimal("100"),
            "SELL_A": Decimal("100"),
            "BUY_Z": Decimal("100"),
            "BUY_A": Decimal("100"),
        },
        target_weights={
            "BUY_Z": Decimal("0.49"),
            "BUY_A": Decimal("0.49"),
        },
    )

    assert [(item.side, item.security_id) for item in plan.intents] == [
        (core.SELL, "SELL_A"),
        (core.SELL, "SELL_Z"),
        (core.BUY, "BUY_A"),
        (core.BUY, "BUY_Z"),
    ]
    assert [item.ordinal for item in plan.intents] == [1, 2, 3, 4]


def test_initialize_and_pre_submit_are_independent_backtest_only_guards():
    plan = _plan()
    registered = core.register_idempotent_rebalance(plan)

    assert core.validate_backtest_initialize(live_mode=False) is True
    assert (
        core.validate_backtest_pre_submit(
            live_mode=False,
            candidate_plan=plan,
            registered_plan=registered,
        )
        is registered
    )
    _assert_refusal(
        core.LIVE_MODE_REFUSAL,
        core.validate_backtest_initialize,
        live_mode=True,
    )
    _assert_refusal(
        core.LIVE_MODE_REFUSAL,
        core.validate_backtest_pre_submit,
        live_mode=True,
        candidate_plan=plan,
        registered_plan=registered,
    )


def test_same_rebalance_retry_is_idempotent_and_conflicts_refuse():
    original = _plan()
    exact_retry = _plan()
    changed_retry = _plan(starting_cash=Decimal("2010"))
    different_scope = _plan(rebalance_id="rebalance-2026-01-12")

    assert (
        core.register_idempotent_rebalance(
            exact_retry, existing_plan=original
        )
        is original
    )
    _assert_refusal(
        core.REBALANCE_REUSE_REFUSAL,
        core.register_idempotent_rebalance,
        changed_retry,
        existing_plan=original,
    )
    _assert_refusal(
        core.IDEMPOTENCY_SCOPE_REFUSAL,
        core.register_idempotent_rebalance,
        different_scope,
        existing_plan=original,
    )


def test_full_fills_charge_exact_ten_bps_each_side_and_stay_cash_only():
    plan = _plan()
    summary = core.summarize_order_lifecycle(plan, _terminal_events(plan))

    assert summary.sell_filled_notional == Decimal("4200")
    assert summary.buy_filled_notional == Decimal("5850")
    assert summary.total_filled_notional == Decimal("10050")
    assert summary.modeled_fee_amount == Decimal("10.050")
    assert summary.actual_engine_fee_amount == Decimal("10.050")
    assert summary.actual_engine_fee_effective_bps_per_side == Decimal(10)
    assert summary.modeled_minus_actual_fee_amount == 0
    assert summary.fee_mismatch is False
    assert summary.two_sided_turnover == Decimal("0.8375")
    assert summary.final_cash == Decimal("339.950")
    assert summary.final_cash >= 0
    assert summary.filled_order_count == 2
    assert summary.canceled_order_count == 0
    assert summary.invalid_order_count == 0
    assert summary.orders_with_any_fill_count == 2
    assert summary.target_weight_l1_error > 0


def test_partial_fills_then_cancel_aggregate_once_and_duplicate_retry_is_ignored():
    plan = _plan()
    sell = _sell(plan)
    buy = _buy(plan)
    events = (
        _event(
            sell,
            event_id="sell-part-1",
            status=core.PARTIALLY_FILLED,
            quantity=20,
            price=Decimal("101"),
        ),
        _event(
            sell,
            event_id="sell-part-2",
            status=core.FILLED,
            quantity=22,
            price=Decimal("100.5"),
        ),
        _event(
            buy,
            event_id="buy-part",
            status=core.PARTIALLY_FILLED,
            quantity=100,
            price=Decimal("50"),
        ),
        core.FillEvent(
            event_id="buy-cancel",
            rebalance_id=plan.rebalance_id,
            client_order_id=buy.client_order_id,
            status=core.CANCELED,
            fill_quantity=0,
            fill_price=None,
        ),
    )
    with_duplicate = events[:1] + events

    summary = core.summarize_order_lifecycle(plan, events)
    duplicate_summary = core.summarize_order_lifecycle(plan, with_duplicate)

    assert summary == duplicate_summary
    assert summary.fill_event_count == 4
    assert summary.filled_order_count == 1
    assert summary.canceled_order_count == 1
    assert summary.orders_with_any_fill_count == 2
    assert summary.sell_filled_notional == Decimal("4231")
    assert summary.buy_filled_notional == Decimal("5000")
    assert summary.modeled_fee_amount == Decimal("9.231")
    assert summary.actual_engine_fee_amount == Decimal("9.231")
    assert summary.fee_mismatch is False


def test_invalid_is_terminal_and_has_no_fabricated_fill_or_fee():
    plan = _plan()
    sell = _sell(plan)
    buy = _buy(plan)
    events = (
        _event(sell, event_id="sell-filled"),
        core.FillEvent(
            event_id="buy-invalid",
            rebalance_id=plan.rebalance_id,
            client_order_id=buy.client_order_id,
            status=core.INVALID,
            fill_quantity=0,
            fill_price=None,
        ),
    )

    summary = core.summarize_order_lifecycle(plan, events)

    assert summary.filled_order_count == 1
    assert summary.invalid_order_count == 1
    assert summary.buy_filled_notional == 0
    assert summary.modeled_fee_amount == Decimal("4.200")
    assert summary.actual_engine_fee_amount == Decimal("4.200")


def test_partial_fill_actual_fee_differential_is_exact_and_load_bearing():
    plan = _plan()
    sell = _sell(plan)
    events = (
        _event(
            sell,
            event_id="partial-fee-one",
            status=core.PARTIALLY_FILLED,
            quantity=20,
            price=Decimal("100"),
            fee_amount=Decimal("4.2"),
        ),
        _event(
            sell,
            event_id="partial-fee-two",
            status=core.FILLED,
            quantity=22,
            price=Decimal("100"),
            fee_amount=Decimal("4.2"),
        ),
        core.FillEvent(
            event_id="buy-cancel",
            rebalance_id=plan.rebalance_id,
            client_order_id=_buy(plan).client_order_id,
            status=core.CANCELED,
            fill_quantity=0,
            fill_price=None,
        ),
    )

    summary = core.summarize_order_lifecycle(plan, events)

    assert summary.total_filled_notional == Decimal("4200")
    assert summary.modeled_fee_amount == Decimal("4.2")
    assert summary.actual_engine_fee_amount == Decimal("8.4")
    assert summary.actual_engine_fee_effective_bps_per_side == Decimal("20")
    assert summary.modeled_minus_actual_fee_amount == Decimal("-4.2")
    assert summary.fee_mismatch is True


def test_offsetting_per_fill_fee_errors_cannot_hide_behind_equal_total():
    plan = _plan()
    sell = _sell(plan)
    events = (
        _event(
            sell,
            event_id="offset-fee-one",
            status=core.PARTIALLY_FILLED,
            quantity=20,
            price=Decimal("100"),
            fee_amount=Decimal("3"),
        ),
        _event(
            sell,
            event_id="offset-fee-two",
            status=core.FILLED,
            quantity=22,
            price=Decimal("100"),
            fee_amount=Decimal("1.2"),
        ),
        core.FillEvent(
            event_id="offset-buy-cancel",
            rebalance_id=plan.rebalance_id,
            client_order_id=_buy(plan).client_order_id,
            status=core.CANCELED,
            fill_quantity=0,
            fill_price=None,
        ),
    )

    summary = core.summarize_order_lifecycle(plan, events)

    assert summary.modeled_fee_amount == Decimal("4.2")
    assert summary.actual_engine_fee_amount == Decimal("4.2")
    assert summary.modeled_minus_actual_fee_amount == 0
    assert summary.actual_engine_fee_effective_bps_per_side == Decimal(10)
    assert summary.fee_mismatch is True


def test_summary_is_aggregate_only_and_ledger_digest_is_deterministic():
    plan = _plan()
    events = _terminal_events(plan)
    first = core.summarize_order_lifecycle(plan, events).to_record()
    second = core.summarize_order_lifecycle(plan, events).to_record()
    encoded = json.dumps(first, sort_keys=True)

    assert first == second
    assert len(first["order_ledger_sha256"]) == 64
    assert "TICKER_ALPHA_RAW" not in encoded
    assert "TICKER_BETA_RAW" not in encoded
    assert plan.rebalance_id not in encoded
    assert not any(
        "ticker" in key.lower() or "security" in key.lower()
        for key in first
    )


@pytest.mark.parametrize("live_mode", [0, None, "false"])
def test_live_flag_type_refusal_is_direct(live_mode):
    _assert_refusal(
        core.LIVE_FLAG_TYPE_REFUSAL,
        core.validate_backtest_initialize,
        live_mode=live_mode,
    )


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"rebalance_id": ""}, core.REBALANCE_ID_REFUSAL),
        ({"starting_cash": Decimal("NaN")}, core.CASH_REFUSAL),
        ({"target_weights": {}}, core.TARGET_MAP_REFUSAL),
        (
            {
                "target_weights": {
                    "TICKER_ALPHA_RAW": Decimal("0.49"),
                    "TICKER_BETA_RAW": Decimal("NaN"),
                }
            },
            core.TARGET_WEIGHT_REFUSAL,
        ),
        (
            {
                "target_weights": {
                    "TICKER_ALPHA_RAW": Decimal("0.48"),
                    "TICKER_BETA_RAW": Decimal("0.49"),
                }
            },
            core.TARGET_GROSS_REFUSAL,
        ),
        ({"current_quantities": []}, core.QUANTITY_MAP_REFUSAL),
        (
            {"current_quantities": {"TICKER_ALPHA_RAW": True}},
            core.QUANTITY_REFUSAL,
        ),
        (
            {
                "current_quantities": {" ": 1},
                "reference_prices": {
                    " ": Decimal("100"),
                    "TICKER_ALPHA_RAW": Decimal("100"),
                    "TICKER_BETA_RAW": Decimal("50"),
                },
            },
            core.SECURITY_ID_REFUSAL,
        ),
        ({"reference_prices": []}, core.PRICE_MAP_REFUSAL),
        (
            {
                "reference_prices": {
                    "TICKER_ALPHA_RAW": Decimal("100")
                }
            },
            core.PRICE_MAP_REFUSAL,
        ),
        (
            {
                "reference_prices": {
                    "TICKER_ALPHA_RAW": Decimal("100"),
                    "TICKER_BETA_RAW": Decimal("0"),
                }
            },
            core.PRICE_REFUSAL,
        ),
        (
            {
                "starting_cash": Decimal("0"),
                "current_quantities": {"TICKER_ALPHA_RAW": 0},
                "reference_prices": {"TICKER_ALPHA_RAW": Decimal("100")},
                "target_weights": {"TICKER_ALPHA_RAW": Decimal("0.98")},
            },
            core.EQUITY_REFUSAL,
        ),
    ],
)
def test_every_planner_refusal_is_direct(overrides, expected):
    kwargs = {
        "rebalance_id": "rebalance-2026-01-05",
        "starting_cash": Decimal("2000"),
        "current_quantities": {"TICKER_ALPHA_RAW": 100},
        "reference_prices": {
            "TICKER_ALPHA_RAW": Decimal("100"),
            "TICKER_BETA_RAW": Decimal("50"),
        },
        "target_weights": {
            "TICKER_ALPHA_RAW": Decimal("0.49"),
            "TICKER_BETA_RAW": Decimal("0.49"),
        },
    }
    kwargs.update(overrides)

    _assert_refusal(expected, core.plan_rebalance, **kwargs)


def test_plan_type_integrity_and_registration_refusals_are_direct():
    plan = _plan()
    corrupted = dataclasses.replace(plan, plan_sha256="0" * 64)

    _assert_refusal(
        core.PLAN_TYPE_REFUSAL,
        core.register_idempotent_rebalance,
        object(),
    )
    _assert_refusal(
        core.PLAN_INTEGRITY_REFUSAL,
        core.register_idempotent_rebalance,
        corrupted,
    )
    _assert_refusal(
        core.UNREGISTERED_PLAN_REFUSAL,
        core.validate_backtest_pre_submit,
        live_mode=False,
        candidate_plan=plan,
        registered_plan=None,
    )


def test_event_collection_type_and_event_type_refusals_are_direct():
    plan = _plan()
    _assert_refusal(
        core.EVENT_COLLECTION_REFUSAL,
        core.summarize_order_lifecycle,
        plan,
        [],
    )
    _assert_refusal(
        core.EVENT_TYPE_REFUSAL,
        core.summarize_order_lifecycle,
        plan,
        ({},),
    )


def test_event_identity_status_and_shape_refusals_are_direct():
    plan = _plan()
    sell = _sell(plan)
    cases = (
        (
            core.EVENT_ID_REFUSAL,
            _event(sell, event_id=""),
        ),
        (
            core.EVENT_REBALANCE_REFUSAL,
            _event(sell, event_id="wrong-run", rebalance_id="other"),
        ),
        (
            core.EVENT_REBALANCE_REFUSAL,
            _event(sell, event_id="bad-run-type", rebalance_id=[]),
        ),
        (
            core.UNKNOWN_ORDER_REFUSAL,
            _event(sell, event_id="wrong-order", client_order_id="unknown"),
        ),
        (
            core.UNKNOWN_ORDER_REFUSAL,
            _event(sell, event_id="bad-order-type", client_order_id=[]),
        ),
        (
            core.STATUS_REFUSAL,
            dataclasses.replace(
                _event(sell, event_id="status"), status="Submitted"
            ),
        ),
        (
            core.STATUS_REFUSAL,
            dataclasses.replace(
                _event(sell, event_id="status-type"), status=[]
            ),
        ),
        (
            core.FILL_SHAPE_REFUSAL,
            dataclasses.replace(
                _event(sell, event_id="shape"), fill_quantity=True
            ),
        ),
        (
            core.FEE_SHAPE_REFUSAL,
            dataclasses.replace(
                _event(sell, event_id="fee-negative"),
                engine_fee_amount=Decimal("-0.01"),
            ),
        ),
        (
            core.FEE_SHAPE_REFUSAL,
            dataclasses.replace(
                _event(sell, event_id="fee-type"),
                engine_fee_amount="4.2",
            ),
        ),
        (
            core.FEE_SHAPE_REFUSAL,
            dataclasses.replace(
                _event(sell, event_id="fee-currency"),
                engine_fee_currency="EUR",
            ),
        ),
    )
    for expected, event in cases:
        _assert_refusal(
            expected,
            core.summarize_order_lifecycle,
            plan,
            (event,),
        )


def test_conflicting_duplicate_and_post_terminal_event_refusals_are_direct():
    plan = _plan()
    sell = _sell(plan)
    duplicate_one = _event(
        sell,
        event_id="duplicate",
        status=core.PARTIALLY_FILLED,
        quantity=1,
    )
    duplicate_two = dataclasses.replace(duplicate_one, fill_quantity=2)
    terminal = _event(sell, event_id="terminal")
    after_terminal = core.FillEvent(
        event_id="after-terminal",
        rebalance_id=plan.rebalance_id,
        client_order_id=sell.client_order_id,
        status=core.CANCELED,
        fill_quantity=0,
        fill_price=None,
    )

    _assert_refusal(
        core.DUPLICATE_EVENT_REFUSAL,
        core.summarize_order_lifecycle,
        plan,
        (duplicate_one, duplicate_two),
    )
    _assert_refusal(
        core.TERMINAL_EVENT_REFUSAL,
        core.summarize_order_lifecycle,
        plan,
        (terminal, after_terminal),
    )


def test_fill_quantity_and_status_refusals_are_direct():
    plan = _plan()
    sell = _sell(plan)
    cases = (
        (
            core.FILL_OVERRUN_REFUSAL,
            _event(
                sell,
                event_id="overrun",
                quantity=sell.quantity + 1,
            ),
        ),
        (
            core.PARTIAL_STATUS_REFUSAL,
            _event(
                sell,
                event_id="partial-complete",
                status=core.PARTIALLY_FILLED,
            ),
        ),
        (
            core.FILLED_STATUS_REFUSAL,
            _event(
                sell,
                event_id="filled-short",
                quantity=sell.quantity - 1,
            ),
        ),
    )
    for expected, event in cases:
        _assert_refusal(
            expected,
            core.summarize_order_lifecycle,
            plan,
            (event,),
        )


def test_actual_fill_that_would_borrow_cash_refuses_even_in_backtest():
    plan = _plan()
    buy = _buy(plan)
    expensive_buy = _event(
        buy,
        event_id="expensive-buy",
        price=Decimal("100"),
    )

    _assert_refusal(
        core.MARGIN_REFUSAL,
        core.summarize_order_lifecycle,
        plan,
        (expensive_buy,),
    )


def test_nonterminal_order_refuses_closed_lifecycle_summary():
    plan = _plan()
    sell = _sell(plan)
    partial = _event(
        sell,
        event_id="still-partial",
        status=core.PARTIALLY_FILLED,
        quantity=1,
    )

    _assert_refusal(
        core.INCOMPLETE_LIFECYCLE_REFUSAL,
        core.summarize_order_lifecycle,
        plan,
        (partial,),
    )
    open_summary = core.summarize_order_lifecycle(
        plan, (partial,), require_all_terminal=False
    )
    assert open_summary.fill_event_count == 1
