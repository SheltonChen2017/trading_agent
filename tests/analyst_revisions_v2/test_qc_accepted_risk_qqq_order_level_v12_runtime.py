import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_order_level_core as orders,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_order_level_forced_exit as forced_exit,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_qc_runtime as legacy,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v12_qc_runtime as runtime,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_qqq_order_level_runtime as fixtures,
)


def _runtime(algorithm=None, profile_id=runtime.FORCED_EXIT_PROFILE_2026_ID):
    algorithm = algorithm or fixtures._Algorithm()
    return runtime.AcceptedRiskQqqOrderLevelV12QcRuntime(
        algorithm,
        activation_manifest_key="arv2/x/transport-manifest.json",
        activation_manifest_sha256="a" * 64,
        activation_manifest_byte_count=1,
        profile_id=profile_id,
        authority_benchmark_symbol=fixtures._Symbol("SPY-SID", "SPY"),
        qqq_benchmark_symbol=fixtures._Symbol("QQQ-SID", "QQQ"),
        qqq_constituent_universe=SimpleNamespace(
            symbol=fixtures._Symbol("QQQU-SID")
        ),
        minute_resolution="Minute",
        raw_normalization="Raw",
        trade_bar_type="TradeBar",
        daily_resolution="Daily",
        total_return_normalization="TotalReturn",
        fee_model_factory=lambda: "ten-bps",
        slippage_model_factory=lambda: "zero",
        order_status_enum=fixtures._OpaqueOrderStatus,
    )


def _forced_ready(quantity=5):
    algorithm = fixtures._Algorithm()
    symbol = fixtures._Symbol("A-SID", "A")
    security = fixtures._Security(symbol)
    security.is_delisted = True
    algorithm.securities[symbol] = security
    algorithm.portfolio.quantities["A-SID"] = 0
    value = _runtime(algorithm)
    value._resolution = fixtures._Resolution({"a": symbol})
    value._configured_security_ids.add("A-SID")
    return value, algorithm, symbol, security, quantity


def _event(symbol, **updates):
    values = {
        "order_id": 71,
        "id": 19,
        "status": fixtures._OpaqueOrderStatus.FILLED,
        "symbol": symbol,
        "message": forced_exit.FORCED_DELISTING_TAG,
        "fill_quantity": -5,
        "fill_price": Decimal("12.50"),
        "order_fee": fixtures._order_fee("0", "QCC"),
    }
    values.update(updates)
    return SimpleNamespace(**values)


def _engine_order(symbol, **updates):
    values = {
        "id": 71,
        "symbol": symbol,
        "tag": forced_exit.FORCED_DELISTING_TAG,
        "quantity": -5,
    }
    values.update(updates)
    return SimpleNamespace(**values)


def _forced_state(value):
    return (
        value._forced_delisting_ledger,
        value._pending_preopen,
        value._forced_exit_invalidated_pending_plan_count,
        tuple(value._lifecycle_records),
    )


def test_v12_profiles_are_exact_v11_extensions_and_legacy_profiles_do_not_move():
    assert runtime.FORCED_EXIT_PROFILE_IDS == (
        "arv2-qqq-order-level-tilt-2025-cutoff-v12",
        "arv2-qqq-order-level-tilt-2026-cutoff-v12",
    )
    expected = {
        runtime.FORCED_EXIT_PROFILE_2025_ID: (
            "c92169a8fd0d2925fad971aa51aa643b1a028c9f48aab61dc227ac90dd49d53d"
        ),
        runtime.FORCED_EXIT_PROFILE_2026_ID: (
            "15c52dcaafae36d7ab8785e95809781a14427c09288ddc7c5c0c859c8b1a2058"
        ),
    }
    for profile_id, digest in expected.items():
        profile = runtime.require_qqq_order_level_profile(profile_id)
        assert profile["schema"] == runtime.FORCED_EXIT_PROFILE_SCHEMA
        assert profile["profile_sha256"] == digest
        assert profile["qc_order_status_codec"] == (
            "exact_System.Enum_reflection_name_numeric_type_and_value_map"
        )
        assert profile["pending_preopen_forced_delisting_policy"] == (
            "invalidate_entire_frozen_rebalance_never_rewrite_or_reweight"
        )
        assert runtime.expected_custom_summary_statistic_names(profile_id) == (
            legacy.AGGREGATES_STATISTIC_NAME,
            legacy.META_STATISTIC_NAME,
        )
    assert legacy.require_qqq_order_level_profile(
        legacy.REFLECTED_TICKET_PROFILE_2025_ID
    )["profile_sha256"] == (
        "4f2213e70d19479f7757141727aa7c977a2f6210014094e4c9ac9c6dd3871917"
    )
    assert legacy.require_qqq_order_level_profile(
        legacy.REFLECTED_TICKET_PROFILE_2026_ID
    )["profile_sha256"] == (
        "980759a4a5e996b21349ee53e9a5b6343e1a8b9914006907fec29de8e77c2307"
    )


def test_exact_engine_delisting_fill_is_accounted_separately_and_redacted():
    value, _algorithm, symbol, _security, quantity = _forced_ready()
    value.on_order_event(
        _event(symbol, fill_quantity=-quantity),
        engine_order=_engine_order(symbol, quantity=-quantity),
    )

    forced = forced_exit.forced_delisting_summary(
        value._forced_delisting_ledger
    )
    assert forced["order_count"] == 1
    assert forced["absolute_filled_quantity"] == 5
    assert forced["filled_notional"] == "62.5"
    assert forced["actual_engine_fee_amount"] == "0"
    assert forced["raw_order_rows_in_summary"] is False
    assert forced["raw_security_rows_in_summary"] is False
    assert "A-SID" not in json.dumps(forced, sort_keys=True)
    assert value._submitted_order_count == 0
    assert value._lifecycle_records == []


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("missing_order", forced_exit.UNKNOWN_ORDER_REFUSAL),
        ("not_delisted", forced_exit.UNKNOWN_ORDER_REFUSAL),
        ("unconfigured", forced_exit.UNKNOWN_ORDER_REFUSAL),
        ("unmapped", forced_exit.UNKNOWN_ORDER_REFUSAL),
        ("canonical_symbol", forced_exit.UNKNOWN_ORDER_REFUSAL),
        ("order_id", forced_exit.UNKNOWN_ORDER_REFUSAL),
        ("order_symbol", forced_exit.UNKNOWN_ORDER_REFUSAL),
        ("security_symbol", forced_exit.UNKNOWN_ORDER_REFUSAL),
        ("event_message", forced_exit.UNKNOWN_ORDER_REFUSAL),
        ("order_tag", forced_exit.UNKNOWN_ORDER_REFUSAL),
        ("status", forced_exit.STATUS_REFUSAL),
    ),
)
def test_every_forced_exit_identity_guard_refuses_without_state_change(
    mutation, message,
):
    value, algorithm, symbol, security, _quantity = _forced_ready()
    event = _event(symbol)
    order = _engine_order(symbol)
    if mutation == "missing_order":
        order = None
    elif mutation == "not_delisted":
        security.is_delisted = False
    elif mutation == "unconfigured":
        value._configured_security_ids.clear()
    elif mutation == "unmapped":
        value._resolution = fixtures._Resolution({})
    elif mutation == "canonical_symbol":
        value._resolution.by_security["a"] = fixtures._Symbol("B-SID", "B")
    elif mutation == "order_id":
        order.id = 72
    elif mutation == "order_symbol":
        order.symbol = fixtures._Symbol("B-SID", "B")
    elif mutation == "security_symbol":
        security.symbol = fixtures._Symbol("B-SID", "B")
    elif mutation == "event_message":
        event.message = "Liquidate from Delisting"
    elif mutation == "order_tag":
        order.tag = "Liquidate from Delisting"
    elif mutation == "status":
        event.status = fixtures._OpaqueOrderStatus.SUBMITTED
    before = _forced_state(value)
    with pytest.raises(runtime.AcceptedRiskQqqOrderLevelQcRuntimeError) as caught:
        value.on_order_event(event, engine_order=order)
    assert str(caught.value) == message
    assert _forced_state(value) == before


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("order_id", True, "order-level QC event order identity changed"),
        ("order_id", -1, "order-level QC event order identity changed"),
        ("id", True, "order-level QC event identity changed"),
        ("id", "19", "order-level QC event identity changed"),
    ),
)
def test_forced_exit_event_identifiers_are_exact_nonnegative_integers(
    field, value, message,
):
    runtime_value, _algorithm, symbol, _security, _quantity = _forced_ready()
    event = _event(symbol)
    setattr(event, field, value)
    before = _forced_state(runtime_value)
    with pytest.raises(runtime.AcceptedRiskQqqOrderLevelQcRuntimeError) as caught:
        runtime_value.on_order_event(event, engine_order=_engine_order(symbol))
    assert str(caught.value) == message
    assert _forced_state(runtime_value) == before


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("engine_quantity", "order-level forced delisting order quantity changed"),
        (
            "portfolio_quantity",
            "order-level forced delisting portfolio quantity is not exact zero",
        ),
        ("partial_close", forced_exit.INCOMPLETE_CLOSE_REFUSAL),
        ("over_close", forced_exit.OVER_CLOSE_REFUSAL),
        ("fractional", forced_exit.QUANTITY_REFUSAL),
        ("negative_price", forced_exit.PRICE_REFUSAL),
        ("nonzero_fee", forced_exit.FEE_REFUSAL),
        ("wrong_fee_currency", forced_exit.FEE_REFUSAL),
    ),
)
def test_forced_exit_economics_are_exact_and_atomic(mutation, message):
    value, algorithm, symbol, _security, _quantity = _forced_ready()
    event = _event(symbol)
    order = _engine_order(symbol)
    if mutation == "engine_quantity":
        order.quantity = -4
    elif mutation == "portfolio_quantity":
        algorithm.portfolio.quantities["A-SID"] = 1
    elif mutation == "partial_close":
        value._pending_preopen = ("2026-01-05", orders.plan_rebalance(
            rebalance_id="partial-close-authority",
            starting_cash=Decimal("10000"),
            current_quantities={"a": 5},
            reference_prices={"a": Decimal("100")},
            target_weights={"a": Decimal("0.98")},
        ))
        event.fill_quantity = -4
        order.quantity = -4
    elif mutation == "over_close":
        value._pending_preopen = ("2026-01-05", orders.plan_rebalance(
            rebalance_id="over-close-authority",
            starting_cash=Decimal("10000"),
            current_quantities={"a": 5},
            reference_prices={"a": Decimal("100")},
            target_weights={"a": Decimal("0.98")},
        ))
        event.fill_quantity = -6
        order.quantity = -6
    elif mutation == "fractional":
        event.fill_quantity = Decimal("-4.5")
        order.quantity = Decimal("-4.5")
    elif mutation == "negative_price":
        event.fill_price = Decimal("-0.01")
    elif mutation == "nonzero_fee":
        event.order_fee = fixtures._order_fee("0.01", "QCC")
    elif mutation == "wrong_fee_currency":
        event.order_fee = fixtures._order_fee("0", "USD")
    before = _forced_state(value)
    with pytest.raises(runtime.AcceptedRiskQqqOrderLevelQcRuntimeError) as caught:
        value.on_order_event(event, engine_order=order)
    assert str(caught.value) == message
    assert _forced_state(value) == before


def test_known_strategy_order_stays_on_v11_lifecycle_path():
    algorithm = fixtures._Algorithm()
    symbol = fixtures._Symbol("A-SID", "A")
    value = _runtime(algorithm)
    value._resolution = fixtures._Resolution({"a": symbol})
    value._submit_plan(fixtures._single_buy_plan())

    value.on_order_event(
        SimpleNamespace(
            order_id=1,
            id=7,
            status=fixtures._OpaqueOrderStatus.FILLED,
            fill_quantity=98,
            fill_price=Decimal("100"),
            order_fee=fixtures._order_fee("9.8"),
        ),
        engine_order=SimpleNamespace(id=-1),
    )
    assert tuple(item.status for item in value._open_plan_events) == ("Filled",)
    assert forced_exit.forced_delisting_summary(
        value._forced_delisting_ledger
    )["order_count"] == 0


def test_synchronous_known_strategy_callback_keeps_v11_ticket_staging():
    class SynchronousAlgorithm(fixtures._Algorithm):
        runtime = None

        def market_on_open_order(self, symbol, quantity, *, tag):
            self.orders.append((symbol.value, quantity, tag))
            self.runtime.on_order_event(SimpleNamespace(
                order_id=1,
                id=7,
                status=fixtures._OpaqueOrderStatus.FILLED,
                fill_quantity=98,
                fill_price=Decimal("100"),
                order_fee=fixtures._order_fee("9.8"),
            ))
            return SimpleNamespace(order_id=1)

    algorithm = SynchronousAlgorithm()
    symbol = fixtures._Symbol("A-SID", "A")
    value = _runtime(algorithm)
    algorithm.runtime = value
    value._resolution = fixtures._Resolution({"a": symbol})
    value._submit_plan(fixtures._single_buy_plan())

    assert tuple(item.status for item in value._open_plan_events) == ("Filled",)
    assert value._pending_submission_events is None
    assert forced_exit.forced_delisting_summary(
        value._forced_delisting_ledger
    )["order_count"] == 0


def test_split_like_interplan_quantity_change_keeps_v11_submission_behavior():
    algorithm = fixtures._Algorithm()
    symbol = fixtures._Symbol("A-SID", "A")
    value = _runtime(algorithm)
    value._resolution = fixtures._Resolution({"a": symbol})
    first = fixtures._single_buy_plan()
    value._submit_plan(first)
    value.on_order_event(SimpleNamespace(
        order_id=1,
        id=7,
        status=fixtures._OpaqueOrderStatus.FILLED,
        fill_quantity=98,
        fill_price=Decimal("100"),
        order_fee=fixtures._order_fee("9.8"),
    ))
    value._close_open_plan()

    split_adjusted = orders.plan_rebalance(
        rebalance_id="split-adjusted-next-week",
        starting_cash=Decimal("0"),
        current_quantities={"a": 196},
        reference_prices={"a": Decimal("50")},
        target_weights={"a": Decimal("0.98")},
    )
    value._submit_plan(split_adjusted)
    assert value._open_plan == split_adjusted
    assert len(algorithm.orders) == 2


def test_terminal_strategy_plan_closes_before_separate_forced_exit_accounting():
    algorithm = fixtures._Algorithm()
    symbol = fixtures._Symbol("A-SID", "A")
    security = fixtures._Security(symbol)
    security.is_delisted = True
    algorithm.securities[symbol] = security
    algorithm.portfolio.quantities["A-SID"] = 0
    value = _runtime(algorithm)
    value._resolution = fixtures._Resolution({"a": symbol})
    value._configured_security_ids.add("A-SID")
    value._submit_plan(fixtures._single_buy_plan())
    value.on_order_event(SimpleNamespace(
        order_id=1,
        id=7,
        status=fixtures._OpaqueOrderStatus.FILLED,
        fill_quantity=98,
        fill_price=Decimal("100"),
        order_fee=fixtures._order_fee("9.8"),
    ))

    value.on_order_event(
        _event(symbol, order_id=71, id=19, fill_quantity=-98),
        engine_order=_engine_order(symbol, id=71, quantity=-98),
    )
    assert value._open_plan is None
    assert len(value._lifecycle_records) == 1
    assert value._lifecycle_records[0]["filled_order_count"] == 1
    assert value._submitted_order_count == 1
    assert forced_exit.forced_delisting_summary(
        value._forced_delisting_ledger
    )["absolute_filled_quantity"] == 98


def test_incomplete_active_plan_refuses_without_closing_or_forced_mutation():
    algorithm = fixtures._Algorithm()
    a = fixtures._Symbol("A-SID", "A")
    b = fixtures._Symbol("B-SID", "B")
    security = fixtures._Security(a)
    security.is_delisted = True
    algorithm.securities[a] = security
    algorithm.portfolio.quantities["A-SID"] = 0
    value = _runtime(algorithm)
    value._resolution = fixtures._Resolution({"a": a, "b": b})
    value._configured_security_ids.add("A-SID")
    plan = orders.plan_rebalance(
        rebalance_id="active-incomplete",
        starting_cash=Decimal("10000"),
        current_quantities={"a": 5},
        reference_prices={"a": Decimal("100"), "b": Decimal("100")},
        target_weights={"b": Decimal("0.98")},
    )
    value._submit_plan(plan)
    before = _forced_state(value)
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="every order must have a terminal status",
    ):
        value.on_order_event(
            _event(a), engine_order=_engine_order(a),
        )
    assert value._open_plan is not None
    assert _forced_state(value) == before


def test_valid_forced_exit_invalidates_the_whole_frozen_preopen_plan():
    value, algorithm, symbol, _security, _quantity = _forced_ready()
    other = fixtures._Symbol("B-SID", "B")
    value._resolution = fixtures._Resolution({"a": symbol, "b": other})
    plan = orders.plan_rebalance(
        rebalance_id="frozen-preopen",
        starting_cash=Decimal("10000"),
        current_quantities={"a": 5},
        reference_prices={"a": Decimal("100"), "b": Decimal("100")},
        target_weights={"b": Decimal("0.98")},
    )
    frozen = plan
    value._pending_preopen = ("2026-01-05", plan)
    value._initialized = True
    value.on_order_event(_event(symbol), engine_order=_engine_order(symbol))

    assert frozen == plan
    assert value._pending_preopen is None
    assert value._forced_exit_invalidated_pending_plan_count == 1
    assert algorithm.orders == []
    algorithm.time = algorithm.time.fromisoformat("2026-01-05T09:20:00")
    assert value.on_before_open() is False


def test_failed_forced_exit_leaves_frozen_preopen_plan_untouched():
    value, _algorithm, symbol, _security, _quantity = _forced_ready()
    plan = orders.plan_rebalance(
        rebalance_id="frozen-preopen",
        starting_cash=Decimal("10000"),
        current_quantities={"a": 5},
        reference_prices={"a": Decimal("100")},
        target_weights={"a": Decimal("0.98")},
    )
    pending = ("2026-01-05", plan)
    value._pending_preopen = pending
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="unknown QC order",
    ):
        value.on_order_event(
            _event(symbol, message="wrong"),
            engine_order=_engine_order(symbol),
        )
    assert value._pending_preopen is pending
    assert value._forced_exit_invalidated_pending_plan_count == 0


@pytest.mark.parametrize(
    ("completed", "invalidated", "decisions", "accounting", "expected"),
    (
        (3, 1, 4, True, True),
        (3, 0, 4, True, False),
        (3, 1, 4, False, False),
    ),
)
def test_v12_run_valid_counts_completed_and_invalidated_decisions_once(
    monkeypatch, completed, invalidated, decisions, accounting, expected,
):
    value = _runtime()
    base_summary = {
        "schema": legacy.PROXY_SUMMARY_SCHEMA,
        "execution_failure": False,
        "skipped_unpriced_decision_count": 0,
        "completed_rebalance_count": completed,
        "decision_count": decisions,
        "run_valid": False,
    }
    monkeypatch.setattr(
        legacy.AcceptedRiskQqqOrderLevelQcRuntime,
        "_aggregate_record",
        lambda _self: dict(base_summary),
    )
    original = forced_exit.forced_delisting_summary
    monkeypatch.setattr(
        forced_exit,
        "forced_delisting_summary",
        lambda ledger: {**original(ledger), "accounting_complete": accounting},
    )
    value._forced_exit_invalidated_pending_plan_count = invalidated
    summary = value._aggregate_record()
    assert summary["schema"] == runtime.FORCED_EXIT_SUMMARY_SCHEMA
    assert summary["run_valid"] is expected
    assert summary["forced_exit_invalidated_pending_rebalance_count"] == invalidated


def test_v12_end_callback_writes_exactly_two_bounded_statistics(monkeypatch):
    algorithm = fixtures._Algorithm("2026-09-17")
    value = _runtime(algorithm)
    value._initialized = True
    value._package = SimpleNamespace(
        package_id="package",
        package_sha256="b" * 64,
        activation_manifest_sha256="c" * 64,
    )
    value._resolution = SimpleNamespace(
        resolution_id="resolution",
        resolution_sha256="d" * 64,
    )
    value._decision_count = 0
    value._decision_sessions = ()
    aggregate = {
        "schema": runtime.FORCED_EXIT_SUMMARY_SCHEMA,
        "engine_forced_delisting": forced_exit.forced_delisting_summary(
            value._forced_delisting_ledger
        ),
        "run_valid": True,
    }
    monkeypatch.setattr(value, "_aggregate_record", lambda: aggregate)
    value.on_end_of_algorithm()

    assert tuple(sorted(algorithm.summary_statistics)) == (
        legacy.AGGREGATES_STATISTIC_NAME,
        legacy.META_STATISTIC_NAME,
    )
    meta = json.loads(
        algorithm.summary_statistics[legacy.META_STATISTIC_NAME]
    )
    assert meta["profile_id"] == runtime.FORCED_EXIT_PROFILE_2026_ID
    assert meta["profile_sha256"] == value._profile["profile_sha256"]
    assert json.loads(
        algorithm.summary_statistics[legacy.AGGREGATES_STATISTIC_NAME]
    ) == aggregate
