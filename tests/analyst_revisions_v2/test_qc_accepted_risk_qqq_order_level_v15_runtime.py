import hashlib
import json
from datetime import datetime
from decimal import Decimal, Inexact, localcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_order_level_forced_exit as forced_exit,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_qc_runtime as legacy,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v14_qc_runtime as v14,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v15_qc_runtime as runtime,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_qqq_order_level_runtime as fixtures,
)


V14_SOURCE_SHA256 = (
    "356aea91b861687e35b9d09c65f0f729bf8509bcec791c9f3fbc4a80ebc24001"
)


def _runtime(algorithm=None, profile_id=runtime.ACCOUNT_PROFILE_2026_ID):
    algorithm = algorithm or fixtures._Algorithm()
    return runtime.AcceptedRiskQqqOrderLevelV15QcRuntime(
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


def _forced_ledger(security_id="a", quantity=5):
    return forced_exit.record_forced_delisting_fill(
        forced_exit.empty_forced_delisting_ledger(),
        authenticated_delisted_security_ids=frozenset({security_id}),
        security_id=security_id,
        order_id=71,
        event_id=19,
        event_message=forced_exit.FORCED_DELISTING_TAG,
        order_tag=forced_exit.FORCED_DELISTING_TAG,
        status="Filled",
        maximum_sale_quantity=quantity,
        signed_fill_quantity=Decimal(-quantity),
        fill_price=Decimal("12.50"),
        fee_amount=Decimal(0),
        fee_currency="QCC",
    )


def _target_ready(*, price=None, quantity=0, authenticated=True):
    algorithm = fixtures._Algorithm()
    symbol = fixtures._Symbol("A-SID", "A")
    security = fixtures._Security(symbol)
    security.is_delisted = True
    if price is None:
        security.last_data = None
    else:
        security.price = Decimal(price)
        security.last_data = SimpleNamespace(end_time=algorithm.time)
    algorithm.securities[symbol] = security
    algorithm.portfolio.quantities["A-SID"] = quantity
    value = _runtime(algorithm)
    value._initialized = True
    value._resolution = fixtures._Resolution({"a": symbol})
    value._configured_security_ids.add("A-SID")
    if authenticated:
        value._forced_delisting_ledger = _forced_ledger()
    return value, algorithm, symbol


def test_v15_profiles_are_exact_v14_extensions_and_v14_is_immutable():
    assert runtime.ACCOUNT_PROFILE_IDS == (
        "arv2-qqq-order-level-tilt-2025-cutoff-v15",
        "arv2-qqq-order-level-tilt-2026-cutoff-v15",
    )
    expected_sha256s = {
        runtime.ACCOUNT_PROFILE_2025_ID: (
            "884b61e586dd2265845e751675d3e2eaa452a4d04f3635206acd552455e81738"
        ),
        runtime.ACCOUNT_PROFILE_2026_ID: (
            "13303b1940e3442f01d93020e62c43e196c88ec297ddace97a0f4dc024a14e7a"
        ),
    }
    for profile_id, predecessor_id in zip(
        runtime.ACCOUNT_PROFILE_IDS, v14.DIAGNOSTIC_PROFILE_IDS,
    ):
        profile = runtime.require_qqq_order_level_profile(profile_id)
        predecessor = v14.require_qqq_order_level_profile(predecessor_id)
        assert profile["schema"] == runtime.ACCOUNT_PROFILE_SCHEMA
        assert profile["delisted_zero_holding_target_policy"] == (
            runtime.DELISTED_ZERO_HOLDING_TARGET_POLICY
        )
        assert profile["terminal_account_observation_policy"] == (
            runtime.TERMINAL_ACCOUNT_OBSERVATION_POLICY
        )
        assert profile["terminal_account_ratio_decimal_precision"] == 32_768
        assert profile["profile_sha256"] == expected_sha256s[profile_id]
        for record in (profile, predecessor):
            record.pop("profile_sha256")
            record.pop("schema")
            record.pop("profile_id")
        profile.pop("delisted_zero_holding_target_policy")
        profile.pop("terminal_account_observation_policy")
        profile.pop("terminal_account_ratio_decimal_precision")
        assert profile == predecessor
    assert hashlib.sha256(Path(v14.__file__).read_bytes()).hexdigest() == (
        V14_SOURCE_SHA256
    )


@pytest.mark.parametrize("price", (None, "100"))
def test_authenticated_zero_held_forced_delisted_target_moves_to_proxy(price):
    value, _algorithm, _symbol = _target_ready(price=price)

    plan = value._build_plan(
        "2026-01-02",
        {"a": Decimal("0.10"), legacy._PROXY_ID: Decimal("0.88")},
    )

    assert plan is not None
    assert dict(plan.target_weights) == {legacy._PROXY_ID: Decimal("0.98")}
    assert value._skipped_unpriced_decision_count == 0
    assert value._skipped_unpriced_evidence_records == []
    assert value._retired_delisted_target_records == [{
        "decision_session": "2026-01-02",
        "retired_security_sha256s": [v14._redacted_security_id_sha256("a")],
        "retired_target_weight": "0.1",
    }]


def test_unpriced_target_without_authenticated_forced_exit_still_skips():
    value, _algorithm, _symbol = _target_ready(authenticated=False)

    plan = value._build_plan(
        "2026-01-02",
        {"a": Decimal("0.10"), legacy._PROXY_ID: Decimal("0.88")},
    )

    assert plan is None
    assert value._skipped_unpriced_decision_count == 1
    assert len(value._skipped_unpriced_evidence_records) == 1
    assert value._retired_delisted_target_records == []


def test_retirement_is_not_recorded_when_another_unpriced_target_skips_plan():
    value, algorithm, symbol = _target_ready()
    other_symbol = fixtures._Symbol("B-SID", "B")
    other = fixtures._Security(other_symbol)
    other.last_data = None
    algorithm.securities[other_symbol] = other
    value._resolution = fixtures._Resolution({
        "a": symbol,
        "b": other_symbol,
    })

    plan = value._build_plan(
        "2026-01-02",
        {
            "a": Decimal("0.10"),
            "b": Decimal("0.10"),
            legacy._PROXY_ID: Decimal("0.78"),
        },
    )

    assert plan is None
    assert value._skipped_unpriced_decision_count == 1
    assert value._retired_delisted_target_records == []


def test_authenticated_forced_delisted_holding_may_not_reappear():
    value, _algorithm, _symbol = _target_ready(quantity=1)

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^order-level retired delisted target holding reappeared$",
    ):
        value._build_plan(
            "2026-01-02",
            {"a": Decimal("0.10"), legacy._PROXY_ID: Decimal("0.88")},
        )

    assert value._skipped_unpriced_decision_count == 0
    assert value._retired_delisted_target_records == []


def test_forced_delisted_target_requires_delisted_flag():
    value, algorithm, symbol = _target_ready()
    algorithm.securities[symbol].is_delisted = False

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^order-level retired delisted target authority changed$",
    ):
        value._build_plan(
            "2026-01-02",
            {"a": Decimal("0.10"), legacy._PROXY_ID: Decimal("0.88")},
        )


def test_forced_delisted_target_rejects_positive_ledger_quantity(monkeypatch):
    value, _algorithm, _symbol = _target_ready()
    monkeypatch.setattr(
        forced_exit, "forced_delisting_signed_quantity", lambda *_args: 1
    )

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^order-level retired delisted target authority changed$",
    ):
        value._build_plan(
            "2026-01-02",
            {"a": Decimal("0.10"), legacy._PROXY_ID: Decimal("0.88")},
        )


def test_forced_delisted_target_requires_whole_zero_holding():
    value, _algorithm, _symbol = _target_ready(quantity=Decimal("0.5"))

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^order-level retired delisted target quantity is not whole$",
    ):
        value._build_plan(
            "2026-01-02",
            {"a": Decimal("0.10"), legacy._PROXY_ID: Decimal("0.88")},
        )


def test_retired_target_requires_structural_proxy():
    value, _algorithm, _symbol = _target_ready()

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^order-level retired delisted target lacks structural proxy$",
    ):
        value._build_plan("2026-01-02", {"a": Decimal("0.98")})


def test_v15_target_weights_require_the_same_exact_dict_boundary():
    value, _algorithm, _symbol = _target_ready()
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^order-level V15 target weights are not an exact dict$",
    ):
        value._build_plan(
            "2026-01-02",
            (("a", Decimal("0.10")), (legacy._PROXY_ID, Decimal("0.88"))),
        )


@pytest.mark.parametrize(
    ("target_weights", "message"),
    (
        (
            {"a": Decimal("-0.1"), legacy._PROXY_ID: Decimal("1.08")},
            "order-level V15 target weight changed",
        ),
        (
            {"a": 1, legacy._PROXY_ID: Decimal("-0.02")},
            "order-level V15 target weight changed",
        ),
        (
            {"a": Decimal(0), legacy._PROXY_ID: Decimal("0.98")},
            "order-level V15 target weight changed",
        ),
        (
            {"a": Decimal("0.10"), legacy._PROXY_ID: Decimal("0.87")},
            "order-level V15 target gross changed",
        ),
        (
            {" a": Decimal("0.10"), legacy._PROXY_ID: Decimal("0.88")},
            "order-level V15 target security identity changed",
        ),
    ),
)
def test_invalid_retired_target_cannot_be_laundered_into_proxy(
    target_weights, message,
):
    value, _algorithm, _symbol = _target_ready()

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^" + message + "$",
    ):
        value._build_plan("2026-01-02", target_weights)

    assert value._skipped_unpriced_decision_count == 0
    assert value._retired_delisted_target_records == []


def _terminal_ready(*, first="1000000", prior="1168510.983845"):
    algorithm = fixtures._Algorithm()
    algorithm.time = datetime.fromisoformat("2026-09-18T00:00:00")
    algorithm.portfolio.total_portfolio_value = Decimal("1168243.410845")
    algorithm.portfolio.total_holdings_value = Decimal("1120000")
    algorithm.portfolio.cash = Decimal("48243.410845")
    value = _runtime(algorithm)
    value._strategy_equity_observations = {
        "2026-01-02": Decimal(first),
        legacy.FINAL_EXECUTION_SESSION: Decimal(prior),
    }
    value._gross_exposure_observations = {
        "2026-01-02": Decimal(0),
        legacy.FINAL_EXECUTION_SESSION: Decimal("0.95"),
    }
    value._cash_weight_observations = {
        "2026-01-02": Decimal(1),
        legacy.FINAL_EXECUTION_SESSION: Decimal("0.05"),
    }
    return value, algorithm


def test_terminal_snapshot_replaces_only_the_final_observation_exactly():
    value, algorithm = _terminal_ready()

    value._replace_terminal_account_observation()

    assert value._strategy_equity_observations["2026-01-02"] == Decimal(
        "1000000"
    )
    assert value._strategy_equity_observations[
        legacy.FINAL_EXECUTION_SESSION
    ] == Decimal("1168243.410845")
    assert value._terminal_account_observation_prior_equity == Decimal(
        "1168510.983845"
    )
    assert value._terminal_account_observation_equity == Decimal(
        "1168243.410845"
    )
    assert value._terminal_account_observation_adjustment == Decimal(
        "-267.573"
    )
    assert (
        value._gross_exposure_observations[legacy.FINAL_EXECUTION_SESSION]
        + value._cash_weight_observations[legacy.FINAL_EXECUTION_SESSION]
        == 1
    )
    algorithm.portfolio.total_portfolio_value = Decimal("999999")
    assert value._portfolio_equity() == Decimal("1168243.410845")


def test_terminal_snapshot_is_deterministic_under_hostile_ambient_context():
    value, _algorithm = _terminal_ready()

    with localcontext() as context:
        context.prec = 3
        context.traps[Inexact] = True
        value._replace_terminal_account_observation()

    assert value._strategy_equity_observations[
        legacy.FINAL_EXECUTION_SESSION
    ] == Decimal("1168243.410845")
    assert (
        value._gross_exposure_observations[legacy.FINAL_EXECUTION_SESSION]
        + value._cash_weight_observations[legacy.FINAL_EXECUTION_SESSION]
        == 1
    )


def test_terminal_snapshot_refuses_changed_start_without_mutation():
    value, _algorithm = _terminal_ready(first="999999")
    before = (
        dict(value._strategy_equity_observations),
        dict(value._gross_exposure_observations),
        dict(value._cash_weight_observations),
    )
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^order-level starting account observation changed$",
    ):
        value._replace_terminal_account_observation()
    assert before == (
        value._strategy_equity_observations,
        value._gross_exposure_observations,
        value._cash_weight_observations,
    )
    assert value._terminal_account_observation_adjustment is None


def test_terminal_snapshot_refuses_account_composition_without_mutation():
    value, algorithm = _terminal_ready()
    algorithm.portfolio.cash = Decimal("48243.410844")
    before = (
        dict(value._strategy_equity_observations),
        dict(value._gross_exposure_observations),
        dict(value._cash_weight_observations),
    )

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^order-level terminal account composition changed$",
    ):
        value._replace_terminal_account_observation()

    assert before == (
        value._strategy_equity_observations,
        value._gross_exposure_observations,
        value._cash_weight_observations,
    )
    assert value._terminal_account_observation_adjustment is None


def test_terminal_snapshot_may_be_applied_only_once():
    value, _algorithm = _terminal_ready()
    value._replace_terminal_account_observation()

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^order-level terminal account observation is unavailable$",
    ):
        value._replace_terminal_account_observation()


def test_v15_summary_discloses_retirement_and_terminal_reconciliation(monkeypatch):
    value, _algorithm = _terminal_ready()
    value._replace_terminal_account_observation()
    value._retired_delisted_target_records = [{
        "decision_session": "2026-08-10",
        "retired_security_sha256s": ["a" * 64],
        "retired_target_weight": "0.00125",
    }]
    monkeypatch.setattr(
        v14.AcceptedRiskQqqOrderLevelV14QcRuntime,
        "_aggregate_record",
        lambda _self: {"schema": v14.DIAGNOSTIC_SUMMARY_SCHEMA},
    )

    summary = value._aggregate_record()

    assert summary["schema"] == runtime.ACCOUNT_SUMMARY_SCHEMA
    assert summary["delisted_zero_holding_target_retirement_count"] == 1
    assert summary[
        "delisted_zero_holding_target_retirement_decision_count"
    ] == 1
    assert summary[
        "delisted_zero_holding_target_retired_weight_total"
    ] == "0.00125"
    assert len(summary["delisted_zero_holding_target_path_sha256"]) == 64
    assert summary["terminal_account_observation_prior_equity"] == (
        "1168510.983845"
    )
    assert summary["terminal_account_observation_equity"] == (
        "1168243.410845"
    )
    assert summary["terminal_account_observation_adjustment"] == "-267.573"
    assert "a" * 64 not in json.dumps(summary, sort_keys=True)


def test_end_callback_reconciles_before_aggregate_and_transport(monkeypatch):
    value, algorithm = _terminal_ready()
    value._initialized = True
    value._decision_count = 0
    value._decision_sessions = ()
    value._package = SimpleNamespace(
        package_id="package",
        package_sha256="b" * 64,
        activation_manifest_sha256="c" * 64,
    )
    value._resolution = SimpleNamespace(
        resolution_id="resolution",
        resolution_sha256="d" * 64,
    )

    def aggregate():
        assert value._strategy_equity_observations[
            legacy.FINAL_EXECUTION_SESSION
        ] == Decimal("1168243.410845")
        return {"schema": runtime.ACCOUNT_SUMMARY_SCHEMA, "run_valid": True}

    value._aggregate_record = aggregate
    monkeypatch.setattr(legacy, "MAXIMUM_STATISTIC_BYTES", 8_192)

    value.on_end_of_algorithm()

    assert value.completed is True
    assert json.loads(
        algorithm.summary_statistics[legacy.AGGREGATES_STATISTIC_NAME]
    )["schema"] == runtime.ACCOUNT_SUMMARY_SCHEMA
