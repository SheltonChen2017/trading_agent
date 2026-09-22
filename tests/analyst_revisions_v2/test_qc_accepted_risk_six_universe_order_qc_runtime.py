import hashlib
from datetime import datetime
from decimal import Decimal
from enum import IntEnum
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_order_level_forced_exit as forced,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_simulated_moo_executor as executor,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_qc_runtime as subject,
)


class _OrderStatus(IntEnum):
    NEW = 0
    SUBMITTED = 1
    PARTIALLY_FILLED = 2
    FILLED = 3
    CANCELED = 5
    NONE = 6
    INVALID = 7
    CANCEL_PENDING = 8
    UPDATE_SUBMITTED = 9
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_targets as targets,
)


def test_profiles_bind_every_physical_role_and_their_own_identity():
    observed = []
    for role in targets.ROLES:
        profile = subject.require_six_universe_order_profile(role)
        declared = profile.pop("profile_sha256")
        observed.append(profile["profile_id"])
        assert profile["role"] == role
        assert profile["decision_count"] == 261
        assert profile["target_gross_exposure"] == "0.98"
        assert profile["backtest_only"] is True
        assert profile["live_orders"] is False
        assert profile["trading"] is False
        assert hashlib.sha256(subject._canonical(profile)).hexdigest() == declared

    assert len(set(observed)) == 3


@pytest.mark.parametrize("role", [None, "", "top5", True])
def test_profile_refuses_unfrozen_role(role):
    with pytest.raises(subject.AcceptedRiskSixUniverseOrderQcRuntimeError):
        subject.require_six_universe_order_profile(role)


def test_custom_statistic_inventory_is_exact_and_bounded():
    assert subject.expected_custom_summary_statistic_names(
        targets.ROLE_SIGNAL
    ) == (
        subject.AGGREGATES_STATISTIC_NAME,
        subject.META_STATISTIC_NAME,
    )
    assert subject.MAXIMUM_STATISTIC_BYTES == 8192


def test_population_metrics_reports_return_drawdown_and_zero_volatility():
    result = subject._population_metrics((
        ("2021-01-04", Decimal("100")),
        ("2021-01-05", Decimal("110")),
        ("2021-01-06", Decimal("99")),
    ))

    assert result["cumulative_return"] == "-0.01"
    assert result["maximum_drawdown"] == "-0.1"
    assert result["annualized_volatility"] != "0"
    assert result["zero_rate_sharpe"] == "0"

    flat = subject._population_metrics((
        ("2021-01-04", Decimal("100")),
        ("2021-01-05", Decimal("100")),
    ))
    assert flat["annualized_volatility"] == "0"
    assert flat["zero_rate_sharpe"] is None


def test_population_metrics_refuses_duplicate_or_nonpositive_path():
    with pytest.raises(subject.AcceptedRiskSixUniverseOrderQcRuntimeError):
        subject._population_metrics((
            ("2021-01-04", Decimal("100")),
            ("2021-01-04", Decimal("101")),
        ))
    with pytest.raises(subject.AcceptedRiskSixUniverseOrderQcRuntimeError):
        subject._population_metrics((
            ("2021-01-04", Decimal("100")),
            ("2021-01-05", Decimal("0")),
        ))


def _bare_driver():
    value = object.__new__(subject.AcceptedRiskSixUniverseOrderQcDriver)
    value._session_positions = {
        "2021-01-04": 0,
        "2021-01-05": 1,
        "2021-01-06": 2,
        "2021-01-07": 3,
    }
    return value


class _Symbol:
    def __init__(self, sid):
        self.id = sid


def test_callback_rows_freeze_primitives_and_refuse_conflicting_sid():
    driver = _bare_driver()
    symbol = _Symbol("SID-A")
    row = SimpleNamespace(symbol=symbol, market_cap=Decimal("10"))
    frozen = driver._freeze_fundamental_rows(
        (row,), "fundamental test"
    )
    row.market_cap = Decimal("999")
    assert frozen == (("SID-A", "positive", Decimal("10")),)

    conflict = (
        SimpleNamespace(symbol=symbol, market_cap=Decimal("10")),
        SimpleNamespace(symbol=symbol, market_cap=Decimal("11")),
    )
    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderQcRuntimeError,
        match="conflicts",
    ):
        driver._freeze_fundamental_rows(conflict, "fundamental test")

    constituent = SimpleNamespace(symbol=symbol, weight=Decimal("0.2"))
    constituent_frozen = driver._freeze_constituent_rows(
        (constituent,), "constituent test"
    )
    constituent.weight = Decimal("0.9")
    assert constituent_frozen == (("SID-A", Decimal("0.2")),)


def test_same_session_callback_replay_is_idempotent_but_conflict_refuses():
    driver = _bare_driver()
    driver._initialized = True
    driver._completed = False
    driver._algorithm = SimpleNamespace(
        time=datetime(2021, 1, 4, 12, 0),
    )
    driver._source_row_count = 0
    cache = {}
    symbol = _Symbol("SID-A")
    row = SimpleNamespace(symbol=symbol, market_cap=Decimal("10"))

    driver._cache_collection(
        cache,
        (row,),
        "fundamental test",
        driver._freeze_fundamental_rows,
    )
    driver._cache_collection(
        cache,
        (row,),
        "fundamental test",
        driver._freeze_fundamental_rows,
    )
    assert driver._source_row_count == 1

    row.market_cap = Decimal("11")
    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderQcRuntimeError,
        match="repeated collection conflicts",
    ):
        driver._cache_collection(
            cache,
            (row,),
            "fundamental test",
            driver._freeze_fundamental_rows,
        )


def test_complete_account_paths_require_every_exact_session_and_hash_values():
    sessions = ("2021-01-04", "2021-01-05", "2021-01-06")
    account = {
        session: Decimal(100 + index)
        for index, session in enumerate(sessions)
    }
    gross = {session: Decimal("0.98") for session in sessions}
    account_path, gross_path = subject._complete_account_paths(
        account, gross, sessions
    )
    digest = subject._decimal_path_sha256("test-path-v1", account_path)
    changed = list(account_path)
    changed[1] = (changed[1][0], Decimal("999"))
    assert subject._decimal_path_sha256(
        "test-path-v1", tuple(changed)
    ) != digest
    assert gross_path[0] == (sessions[0], Decimal("0.98"))

    missing = dict(account)
    del missing[sessions[1]]
    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderQcRuntimeError,
        match="session census",
    ):
        subject._complete_account_paths(missing, gross, sessions)


def test_raw_reference_prices_bind_key_payload_symbol_and_session():
    requested = _Symbol("SID-A")
    wrong = _Symbol("SID-B")
    bar = SimpleNamespace(
        symbol=wrong,
        time=datetime(2021, 1, 4, 16, 0),
        close=Decimal("10"),
    )

    class _Batch(dict):
        time = datetime(2021, 1, 4, 16, 0)

    class _History:
        def __getitem__(self, _item):
            return lambda *_args, **_kwargs: (_Batch({requested: bar}),)

    driver = _bare_driver()
    driver._trade_bar_type = object()
    driver._daily_resolution = object()
    driver._raw_normalization = object()
    driver._reference_history_call_count = 0
    driver._algorithm = SimpleNamespace(history=_History())
    driver._ensure_security = lambda _security_id: (requested, object())
    driver._symbol_for_security = lambda _security_id: requested

    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderQcRuntimeError,
        match="payload identity",
    ):
        driver._reference_prices("2021-01-04", ("A",))


def test_missing_raw_reference_price_has_no_stale_security_price_fallback():
    requested = _Symbol("SID-A")

    class _History:
        def __getitem__(self, _item):
            return lambda *_args, **_kwargs: ()

    driver = _bare_driver()
    driver._trade_bar_type = object()
    driver._daily_resolution = object()
    driver._raw_normalization = object()
    driver._reference_history_call_count = 0
    driver._algorithm = SimpleNamespace(history=_History())
    driver._ensure_security = lambda _security_id: (requested, object())

    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderQcRuntimeError,
        match="no stale-price fallback",
    ):
        driver._reference_prices("2021-01-04", ("A",))


def test_split_authority_is_required_for_an_overnight_replan():
    split_type = object()
    symbol = _Symbol("SID-A")
    driver = _bare_driver()
    driver._initialized = True
    driver._completed = False
    driver._algorithm = SimpleNamespace(
        time=datetime(2021, 1, 5, 0, 0),
    )
    driver._split_occurred_type = split_type
    driver._security_by_sid = {"SID-A": "A"}
    driver._security_by_etf_sid = {}
    driver._split_records_by_session = {}
    driver.on_splits({
        symbol: SimpleNamespace(
            type=split_type,
            symbol=symbol,
            split_factor=Decimal("0.5"),
            reference_price=Decimal("50"),
        )
    })
    security = SimpleNamespace(symbol=symbol, price=Decimal("50"))
    driver._ensure_security = lambda _security_id: (symbol, security)
    plan = SimpleNamespace(
        starting_quantities=(("A", 10),),
        target_weights=(("A", Decimal("0.98")),),
        plan_sha256="a" * 64,
    )
    result = driver._holding_drift_replan(
        plan,
        Decimal("100"),
        {"A": 20},
        datetime(2021, 1, 5, 9, 20),
    )
    assert result["reference_prices"] == {"A": Decimal("50")}
    assert len(result["receipt_sha256"]) == 64

    assert driver._holding_drift_replan(
        plan,
        Decimal("100"),
        {"A": 19},
        datetime(2021, 1, 5, 9, 20),
    ) is None

    driver._split_records_by_session = {}
    assert driver._holding_drift_replan(
        plan,
        Decimal("100"),
        {"A": 20},
        datetime(2021, 1, 5, 9, 20),
    ) is None


def test_dynamic_execution_subscription_pruning_requires_flat_and_no_orders():
    symbol = _Symbol("SID-A")
    removed = []
    driver = _bare_driver()
    driver._active_dynamic_sids = {"SID-A"}
    driver._configured_sids = {"SID-A"}
    driver._security_by_sid = {"SID-A": "A"}
    driver._symbol_by_security = {"A": symbol}
    driver._removed_dynamic_security_count = 0
    driver._current_quantity = lambda _security_id: 0
    driver._algorithm = SimpleNamespace(
        transactions=SimpleNamespace(
            get_open_orders=lambda _symbol: (),
        ),
        remove_security=lambda value: removed.append(value),
    )

    driver._prune_execution_subscriptions(set())

    assert removed == [symbol]
    assert driver._active_dynamic_sids == set()
    assert driver._configured_sids == set()
    assert driver._removed_dynamic_security_count == 1


@pytest.mark.parametrize(
    ("quantity", "open_orders", "message"),
    [
        (1, (), "held security"),
        (0, (object(),), "open orders"),
    ],
)
def test_dynamic_subscription_pruning_refuses_holdings_or_open_orders(
    quantity, open_orders, message
):
    symbol = _Symbol("SID-A")
    removed = []
    driver = _bare_driver()
    driver._active_dynamic_sids = {"SID-A"}
    driver._configured_sids = {"SID-A"}
    driver._security_by_sid = {"SID-A": "A"}
    driver._symbol_by_security = {"A": symbol}
    driver._removed_dynamic_security_count = 0
    driver._current_quantity = lambda _security_id: quantity
    driver._algorithm = SimpleNamespace(
        transactions=SimpleNamespace(
            get_open_orders=lambda _symbol: open_orders,
        ),
        remove_security=lambda value: removed.append(value),
    )

    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderQcRuntimeError,
        match=message,
    ):
        driver._prune_execution_subscriptions(set())
    assert removed == []


def test_active_dynamic_minute_subscription_cap_is_load_bearing():
    symbol = _Symbol("SID-NEW")
    driver = _bare_driver()
    driver._symbol_by_security = {"NEW": symbol}
    driver._security_by_etf_sid = {}
    driver._active_dynamic_sids = {
        f"SID-{index}" for index in range(
            subject.MAXIMUM_ACTIVE_DYNAMIC_SECURITY_COUNT
        )
    }
    driver._configured_sids = set()
    driver._maximum_active_dynamic_security_count = len(
        driver._active_dynamic_sids
    )
    driver._minute_resolution = object()
    driver._algorithm = SimpleNamespace(
        add_security=lambda *_args: SimpleNamespace(symbol=symbol),
    )

    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderQcRuntimeError,
        match="active minute-subscription cap",
    ):
        driver._ensure_security("NEW")


def test_per_sleeve_diagnostics_reconcile_all_261_decisions():
    driver = _bare_driver()
    driver._sleeve_diagnostics = subject._empty_sleeve_diagnostics()
    sleeves = tuple(
        SimpleNamespace(
            universe_id=spec.universe_id,
            coverage_valid=True,
            positive_score_count=12,
            selected_security_ids=("A", "B"),
            post_cap_stock_target_count=2,
            etf_target_weight=Decimal("0.01"),
            duplicate_cap_excess_weight=Decimal("0"),
            selection_status="PARTIAL_STOCK_SLOTS_WITH_ETF_FALLBACK",
            coverage_refusal_reasons=(),
        )
        for spec in targets._gate.UNIVERSE_SPECS
    )
    for _index in range(subject.EXPECTED_DECISION_COUNT):
        driver._record_sleeve_diagnostics(sleeves)
    result = driver._frozen_sleeve_diagnostics()
    assert result["schema"] == (
        "arv2-six-universe-order-sleeve-summary-table-v1"
    )
    assert len(result["rows"]) == 6
    positions = {name: index for index, name in enumerate(result["fields"])}
    assert all(
        row[positions["decision_count"]] == subject.EXPECTED_DECISION_COUNT
        and row[positions["coverage_invalid_count"]] == 0
        and row[positions["selected_security_count_sum"]] == 522
        for row in result["rows"]
    )


def test_worst_authorized_aggregate_shape_fits_transport_bound():
    quantities = {"A": 98_000}
    execution = executor.SimulatedMooExecutor(
        current_live_mode=lambda: False,
        order_status_enum=_OrderStatus,
        order_status_to_int=int,
        security_for_id=lambda value: value,
        current_quantity=lambda value: quantities.get(value, 0),
        current_holding_census=lambda: dict(quantities),
        current_cash=lambda: Decimal("20000"),
        submit_market_on_open=lambda *_args, **_kwargs: None,
    )
    execution.prepare_rebalance(
        decision_session="2025-01-02",
        execution_session="2025-01-03",
        target_weights={"A": Decimal("0.98")},
        reference_prices={"A": Decimal("10")},
    )
    execution.on_preopen(datetime(2025, 1, 3, 9, 20))
    execution_aggregate = execution.terminal_aggregate()

    sessions = tuple(f"s{index:04d}" for index in range(1255))
    driver = _bare_driver()
    driver._role = targets.ROLE_SIGNAL
    driver._profile = subject.require_six_universe_order_profile(
        targets.ROLE_SIGNAL
    )
    driver._evaluation_sessions = sessions
    driver._account_observations = {
        session: Decimal("1000000." + str(index % 10) * 15)
        for index, session in enumerate(sessions)
    }
    driver._gross_exposure_observations = {
        session: Decimal("0." + str(index % 9 + 1) * 30)
        for index, session in enumerate(sessions)
    }
    driver._decision_target_sha256s = [
        "d" * 64
    ] * subject.EXPECTED_DECISION_COUNT
    statuses = (
        "COVERAGE_FALLBACK",
        "POSITIVE_SCORE_FLOOR_FALLBACK",
        "DUPLICATE_CAP_ETF_FALLBACK",
        "PARTIAL_STOCK_SLOTS_WITH_ETF_FALLBACK",
        "FULL_STOCK_SLOTS",
    )
    driver._fallback_counts = {name: 261 for name in statuses}
    driver._forced_ledger = forced.empty_forced_delisting_ledger()
    driver._reference_history_call_count = subject.EXPECTED_DECISION_COUNT
    driver._source_row_count = 20_000_000
    driver._active_dynamic_sids = set()
    driver._maximum_active_dynamic_security_count = 128
    driver._removed_dynamic_security_count = 999
    driver._sleeve_diagnostics = subject._empty_sleeve_diagnostics()
    for item in driver._sleeve_diagnostics.values():
        item["decision_count"] = 261
        item["coverage_valid_count"] = 130
        item["positive_score_count_sum"] = 99_999
        item["selected_security_count_sum"] = 9_999
        item["post_cap_stock_target_count_sum"] = 9_999
        item["etf_target_weight_sum"] = Decimal(
            "42.629999999999999999999999999"
        )
        item["duplicate_cap_excess_weight_sum"] = Decimal(
            "1.123456789012345678901234567"
        )
        item["coverage_refusal_reason_counts"] = {
            "TOTAL_REPORTED_WEIGHT_OUT_OF_RANGE": 261,
            "SID_NAME_MAPPING_BELOW_MINIMUM": 261,
            "MARKET_CAP_WEIGHT_COVERAGE_BELOW_MINIMUM": 261,
        }
        item["selection_status_counts"] = {
            name: 261 for name in statuses
        }
    path = SimpleNamespace(
        role=targets.ROLE_SIGNAL,
        decisions=tuple(range(subject.EXPECTED_DECISION_COUNT)),
        target_path_sha256="a" * 64,
        construction_path_sha256="b" * 64,
        to_record=lambda: {"target_path_id": "test-target-path"},
    )
    driver._target_builder = SimpleNamespace(complete_path=lambda: path)
    driver._executor = SimpleNamespace(
        terminal_aggregate=lambda: execution_aggregate
    )

    aggregate = driver._aggregate()

    assert len(subject._canonical(aggregate)) <= subject.MAXIMUM_STATISTIC_BYTES


def test_snapshot_boundary_uses_only_strictly_prior_collection():
    driver = _bare_driver()
    observed, rows = driver._strictly_prior_rows(
        {
            "2021-01-04": ("prior",),
            "2021-01-05": ("same-day",),
        },
        "2021-01-05",
        "test collection",
        maximum_age_sessions=1,
    )

    assert observed == "2021-01-04"
    assert rows == ("prior",)


def test_snapshot_boundary_refuses_future_only_or_stale_collection():
    driver = _bare_driver()
    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderQcRuntimeError,
        match="no strictly prior",
    ):
        driver._strictly_prior_rows(
            {"2021-01-06": ()},
            "2021-01-05",
            "test collection",
            maximum_age_sessions=1,
        )
    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderQcRuntimeError,
        match="frozen age bound",
    ):
        driver._strictly_prior_rows(
            {"2021-01-04": ()},
            "2021-01-07",
            "test collection",
            maximum_age_sessions=1,
        )


def test_runtime_source_is_qc_prelude_safe():
    source = open(subject.__file__, encoding="utf-8").read()
    assert "from __future__" not in source
    compile("from AlgorithmImports import *\n" + source, subject.__file__, "exec")
