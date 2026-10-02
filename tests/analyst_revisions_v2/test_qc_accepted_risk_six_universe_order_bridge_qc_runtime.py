"""Focused red/green gates for the prospective R-181 A3 admission bridge."""

import hashlib
from decimal import Decimal
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_bridge_qc_runtime as subject,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_qc_runtime as base,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_targets as targets,
)


class _Symbol:
    def __init__(self, sid):
        self.id = sid


class _Security:
    def __init__(self, sid, *, effective=None):
        self.symbol = _Symbol(sid)
        self.leverage = Decimal(1)
        self.forced_effective = effective
        self.buying_power_model = SimpleNamespace(
            get_leverage=lambda security: (
                security.leverage if security.forced_effective is None
                else security.forced_effective
            )
        )
        self.calls = []

    def set_data_normalization_mode(self, value):
        self.calls.append(("normalization", value))

    def set_fee_model(self, value):
        self.calls.append(("fee", value))

    def set_slippage_model(self, value):
        self.calls.append(("slippage", value))

    def set_leverage(self, value):
        self.calls.append(("leverage", value))
        self.leverage = Decimal(value)


def _bare_bridge(role=targets.ROLE_SIGNAL):
    driver = object.__new__(subject.AcceptedRiskSixUniverseOrderBridgeQcDriver)
    driver._initialized = True
    driver._completed = False
    driver._bridge_initialized = True
    driver._role = role
    driver._bridge_role = role
    driver._variant = base.CAP90_VARIANT
    profile = subject.require_bridge_profile(role)
    driver._profile = profile
    driver._bridge_profile = profile
    builder = object.__new__(targets.SixUniverseOrderTargetBuilder)
    driver._target_builder = builder
    driver._bridge_builder = builder
    driver._algorithm = SimpleNamespace(live_mode=False)
    driver._bridge_cash_observations = {}
    driver._bridge_event_cash_minimum = None
    driver._bridge_event_cash_count = 0
    return driver


def test_bridge_profile_changes_permission_not_target_economics():
    seen = set()
    for role in targets.ROLES:
        predecessor = base.require_six_universe_order_profile(
            role, variant=base.CAP90_VARIANT
        )
        bridge = subject.require_bridge_profile(role)
        digest = bridge.pop("profile_sha256")
        assert hashlib.sha256(base._canonical(bridge)).hexdigest() == digest
        assert bridge["schema"] == subject.BRIDGE_PROFILE_SCHEMA
        assert bridge["role"] == predecessor["role"] == role
        assert bridge["cap90_predecessor_profile_sha256"] == (
            predecessor["profile_sha256"]
        )
        assert bridge["gate_profile_sha256"] == (
            predecessor["gate_profile_sha256"]
        )
        assert bridge["evaluation_profile_sha256"] == (
            predecessor["evaluation_profile_sha256"]
        )
        assert bridge["target_gross_exposure"] == "0.98"
        assert bridge["admission_leverage"] == "2"
        assert bridge["leverage"] is True
        assert bridge["realized_borrowing_allowed"] is False
        assert bridge["backtest_only"] is True
        assert bridge["live_orders"] is False
        assert bridge["paper_orders"] is False
        assert bridge["funded_orders"] is False
        seen.add(bridge["profile_id"])
        assert subject.expected_bridge_custom_statistic_names(role) == (
            subject.AGGREGATES_STATISTIC_NAME,
            subject.META_STATISTIC_NAME,
        )
        assert base.require_six_universe_order_profile(
            role, variant=base.CAP90_VARIANT
        ) == predecessor
    assert len(seen) == len(targets.ROLES)


@pytest.mark.parametrize(
    ("role", "variant"),
    ((None, subject.BRIDGE_VARIANT), (True, subject.BRIDGE_VARIANT),
     (targets.ROLE_SIGNAL, base.CAP90_VARIANT),
     ("unknown", subject.BRIDGE_VARIANT)),
)
def test_bridge_rejects_wrong_role_or_variant_before_qc_access(role, variant):
    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderBridgeQcRuntimeError,
        match="role or variant is not frozen",
    ):
        subject.AcceptedRiskSixUniverseOrderBridgeQcDriver(
            None, role=role, variant=variant
        )


def test_each_configured_security_gets_verified_two_x_admission_permission():
    driver = _bare_bridge()
    driver._raw_normalization = object()
    driver._fee_model_factory = object
    driver._slippage_model_factory = object
    driver._configured_sids = set()
    security = _Security("SID-STATIC")
    assert driver.configure_security(security) is security
    assert security.leverage == 2
    assert security.calls[-1] == ("leverage", 2)
    assert driver._configured_sids == {"SID-STATIC"}

    # A pending $70k sell cannot fund a simultaneous $70k pre-open buy under
    # a $1m / 1x admission budget when $980k is already held.  The bridge
    # grants temporary admission only; its realized cash/target checks are
    # separately asserted below.
    equity, held_notional, new_buy = (Decimal(1_000_000), Decimal(980_000),
                                      Decimal(70_000))
    assert held_notional + new_buy > equity * Decimal(1)
    assert held_notional + new_buy <= equity * security.leverage


def test_bridge_refuses_an_effective_one_x_model_even_if_setter_returns():
    driver = _bare_bridge()
    driver._raw_normalization = object()
    driver._fee_model_factory = object
    driver._slippage_model_factory = object
    driver._configured_sids = set()
    security = _Security("SID-STATIC", effective=1)
    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderBridgeQcRuntimeError,
        match="effective security leverage is not two",
    ):
        driver.configure_security(security)


def test_dynamic_security_adds_with_two_x_not_frozen_baseline_one_x():
    driver = _bare_bridge()
    driver._raw_normalization = object()
    driver._fee_model_factory = object
    driver._slippage_model_factory = object
    driver._configured_sids = set()
    driver._security_by_etf_sid = {}
    driver._active_dynamic_sids = set()
    driver._maximum_active_dynamic_security_count = 0
    driver._minute_resolution = object()
    symbol = _Symbol("SID-DYNAMIC")
    driver._symbol_by_security = {"DYNAMIC": symbol}
    calls = []
    security = _Security("SID-DYNAMIC")
    driver._algorithm = SimpleNamespace(
        live_mode=False,
        add_security=lambda *args: calls.append(args) or security,
    )
    assert driver._ensure_security("DYNAMIC") == (symbol, security)
    assert len(calls) == 1
    assert calls[0][3] == 2
    assert security.leverage == 2


def test_changed_buying_power_model_refuses_before_reuse_or_order(monkeypatch):
    driver = _bare_bridge()
    symbol = _Symbol("SID-ETF")
    security = _Security("SID-ETF")
    security.leverage = Decimal(2)
    driver._symbol_by_security = {"ETF": symbol}
    driver._security_by_etf_sid = {"SID-ETF": "SID-ETF"}
    driver._active_dynamic_sids = set()
    driver._configured_sids = {"SID-ETF"}
    driver._algorithm.securities = {symbol: security}
    assert driver._ensure_security("ETF") == (symbol, security)
    security.leverage = Decimal(1)  # a later QC model replacement
    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderBridgeQcRuntimeError,
        match="effective security leverage is not two",
    ):
        driver._ensure_security("ETF")
    calls = []
    monkeypatch.setattr(
        base.AcceptedRiskSixUniverseOrderQcDriver,
        "_submit_market_on_open",
        lambda *_args: calls.append("order"),
    )
    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderBridgeQcRuntimeError,
        match="effective security leverage is not two",
    ):
        driver._submit_market_on_open(symbol, 1, "test")
    assert calls == []


@pytest.mark.parametrize(
    ("mutation", "message"),
    (("live", "backtest-only"), ("role", "authority changed"),
     ("profile", "authority changed"), ("builder", "authority changed")),
)
def test_bridge_refuses_mixed_authority_before_preopen_order_callback(
    mutation, message
):
    driver = _bare_bridge()
    submitted = []
    driver._executor = SimpleNamespace(
        on_preopen=lambda _clock: submitted.append("called") or True
    )
    driver._algorithm.time = object()
    if mutation == "live":
        driver._algorithm.live_mode = True
    elif mutation == "role":
        driver._role = targets.ROLE_MATCHED
    elif mutation == "profile":
        driver._profile["admission_leverage"] = "1"
    elif mutation == "builder":
        driver._target_builder = object.__new__(
            targets.SixUniverseOrderTargetBuilder
        )
    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderBridgeQcRuntimeError,
        match=message,
    ):
        driver.on_before_open()
    assert submitted == []


def test_bridge_observes_nonnegative_daily_cash_and_at_most_one_gross():
    driver = _bare_bridge()
    driver._account_observations = {}
    driver._gross_exposure_observations = {}
    portfolio = SimpleNamespace(
        total_portfolio_value=Decimal(1_000_000),
        total_holdings_value=Decimal(980_000),
        cash=Decimal(20_000),
    )
    driver._algorithm.portfolio = portfolio
    driver._observe_account("2021-01-04")
    assert driver._bridge_cash_observations == {
        "2021-01-04": Decimal(20_000)
    }
    assert driver._gross_exposure_observations["2021-01-04"] == (
        Decimal("0.98")
    )
    portfolio.cash = Decimal(-1)
    with pytest.raises(base.AcceptedRiskSixUniverseOrderQcRuntimeError):
        driver._observe_account("2021-01-05")
    assert "2021-01-05" not in driver._bridge_cash_observations
    portfolio.cash = Decimal(20_000)
    portfolio.total_holdings_value = Decimal(1_000_001)
    with pytest.raises(
        subject.AcceptedRiskSixUniverseOrderBridgeQcRuntimeError,
        match="gross exposure exceeds one",
    ):
        driver._observe_account("2021-01-05")


def test_bridge_observes_each_order_event_cash_and_refuses_borrowing(
    monkeypatch
):
    driver = _bare_bridge()
    portfolio = SimpleNamespace(cash=Decimal(20_000))
    driver._algorithm.portfolio = portfolio
    calls = []
    monkeypatch.setattr(
        base.AcceptedRiskSixUniverseOrderQcDriver,
        "on_order_event",
        lambda _self, event: calls.append(event) or True,
    )
    assert driver.on_order_event("filled-buy") is True
    assert driver._bridge_event_cash_count == 1
    assert driver._bridge_event_cash_minimum == Decimal(20_000)
    portfolio.cash = Decimal(-1)
    with pytest.raises(base.AcceptedRiskSixUniverseOrderQcRuntimeError):
        driver.on_order_event("filled-buy-before-sell")
    assert calls == ["filled-buy", "filled-buy-before-sell"]
    assert driver._bridge_event_cash_count == 1


@pytest.mark.parametrize("invalid_cash", ("-1", "NaN", "Infinity", "-Infinity"))
def test_bridge_order_event_refuses_nonfinite_or_negative_cash_before_record(
    monkeypatch, invalid_cash
):
    driver = _bare_bridge()
    driver._algorithm.portfolio = SimpleNamespace(cash=Decimal(invalid_cash))
    calls = []
    monkeypatch.setattr(
        base.AcceptedRiskSixUniverseOrderQcDriver,
        "on_order_event",
        lambda _self, event: calls.append(event) or True,
    )
    with pytest.raises(
        base.AcceptedRiskSixUniverseOrderQcRuntimeError,
        match="six-universe portfolio cash is outside its finite bound",
    ):
        driver.on_order_event("filled-buy")
    assert calls == ["filled-buy"]
    assert driver._bridge_event_cash_count == 0
    assert driver._bridge_event_cash_minimum is None


@pytest.mark.parametrize(
    ("mean_error", "maximum_error", "valid"),
    (("0.019", "0.049", True), ("0.02", "0.05", True),
     ("0.0200001", "0.05", False), ("0.02", "0.0500001", False)),
)
def test_bridge_aggregate_gates_actual_tracking_not_just_order_status(
    monkeypatch, mean_error, maximum_error, valid
):
    driver = _bare_bridge()
    sessions = ("2021-01-04", "2021-01-05")
    driver._evaluation_sessions = sessions
    driver._bridge_cash_observations = {
        session: Decimal(20_000) for session in sessions
    }
    underlying = {
        "run_valid": True,
        "maximum_gross_exposure": "0.98",
        "execution": {
            "run_valid": True,
            "mean_target_weight_l1_error": mean_error,
            "maximum_target_weight_l1_error": maximum_error,
            "target_weight_l1_error_mark_basis": (
                "prior_close_reference_prices_not_realized_open_prices"
            ),
        },
    }
    monkeypatch.setattr(
        base.AcceptedRiskSixUniverseOrderQcDriver,
        "_aggregate", lambda _self: dict(underlying),
    )
    aggregate = driver._aggregate()
    assert aggregate["schema"] == subject.BRIDGE_SUMMARY_SCHEMA
    assert aggregate["admission_leverage"] == "2"
    assert aggregate["target_gross_exposure"] == "0.98"
    assert aggregate["minimum_end_day_cash"] == "20000"
    assert aggregate["daily_cash_nonnegative"] is True
    assert aggregate["order_event_cash_observation_count"] == 0
    assert aggregate["minimum_observed_order_event_cash"] is None
    assert aggregate["order_event_cash_nonnegative"] is True
    assert aggregate["end_day_gross_at_most_one"] is True
    assert aggregate["target_tracking_valid"] is valid
    assert aggregate["run_valid"] is valid


def test_bridge_missing_tracking_metric_is_not_valid_by_default(monkeypatch):
    driver = _bare_bridge()
    driver._evaluation_sessions = ("2021-01-04",)
    driver._bridge_cash_observations = {"2021-01-04": Decimal(20_000)}
    monkeypatch.setattr(
        base.AcceptedRiskSixUniverseOrderQcDriver,
        "_aggregate",
        lambda _self: {
            "run_valid": True,
            "maximum_gross_exposure": "0.98",
            "execution": {
                "mean_target_weight_l1_error": "0.01",
                "target_weight_l1_error_mark_basis": (
                    "prior_close_reference_prices_not_realized_open_prices"
                ),
            },
        },
    )
    with pytest.raises(base.AcceptedRiskSixUniverseOrderQcRuntimeError):
        driver._aggregate()
