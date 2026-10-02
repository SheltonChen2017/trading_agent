import hashlib
import json
from datetime import datetime
from decimal import Decimal, Inexact, localcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_qc_runtime as legacy,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v15_qc_runtime as v15,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v16_qc_runtime as runtime,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_qqq_order_level_runtime as fixtures,
)


V15_SOURCE_SHA256 = (
    "5470b32ea2aa612419a4adad8a2f25dd34308945f84dc61023a3f65f7fa836d1"
)
R169_MEAN_GROSS_EXPOSURE = "0.9627929226578532739058666438"
R169_MEAN_CASH_WEIGHT = "0.03720707734214672609413335543"
R169_EXACT_CASH_COMPLEMENT = "0.0372070773421467260941333562"


def _runtime(algorithm=None, profile_id=runtime.EXPOSURE_PROFILE_2026_ID):
    algorithm = algorithm or fixtures._Algorithm()
    return runtime.AcceptedRiskQqqOrderLevelV16QcRuntime(
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


def _r169_real_base_runtime():
    sessions = ("2026-01-02", legacy.FINAL_EXECUTION_SESSION)
    algorithm = fixtures._Algorithm()
    algorithm.portfolio.total_portfolio_value = Decimal("1168243.410845")
    algorithm.portfolio.total_holdings_value = Decimal("1120000")
    algorithm.portfolio.cash = Decimal("48243.410845")
    value = _runtime(algorithm)
    value._package = SimpleNamespace(
        evaluator_input=SimpleNamespace(session_axis=sessions)
    )
    value._resolution = fixtures._Resolution({
        "a": fixtures._Symbol("A-SID", "A")
    })
    value._resolved_qqq_weights(
        sessions[0],
        {"A-SID": Decimal("1")},
        constituent_age_sessions=1,
    )
    value._decision_count = 1
    value._decision_sessions = sessions[:1]
    value._submitted_order_count = 1
    value._lifecycle_records = [fixtures._lifecycle_record()]
    value._strategy_equity_observations = {
        sessions[0]: Decimal("1000000"),
        sessions[1]: Decimal("1168510.983845"),
    }
    qqq = (
        (sessions[0], Decimal("100")),
        (sessions[1], Decimal("101")),
    )
    value._load_qqq_total_return_observations = (
        lambda expected: qqq if expected == sessions else ()
    )
    value._benchmark_open_observations = {
        sessions[0]: Decimal("100"),
        sessions[1]: Decimal("100"),
    }
    value._gross_exposure_observations = {
        sessions[0]: Decimal("0"),
        sessions[1]: Decimal("0.95"),
    }
    value._cash_weight_observations = {
        sessions[0]: Decimal("1"),
        sessions[1]: Decimal("0.05"),
    }
    value._replace_terminal_account_observation()
    # Reproduce the two exact independently rounded means emitted by R169.
    # The predecessor aggregate computes both means over these real account
    # paths; no aggregate implementation is stubbed or monkeypatched.
    value._gross_exposure_observations = {
        session: Decimal(R169_MEAN_GROSS_EXPOSURE) for session in sessions
    }
    value._cash_weight_observations = {
        session: Decimal(R169_MEAN_CASH_WEIGHT) for session in sessions
    }
    return value


def _end_ready_runtime():
    value = _r169_real_base_runtime()
    value._initialized = True
    value._algorithm.time = datetime.fromisoformat("2026-09-18T00:00:00")
    value._package = SimpleNamespace(
        evaluator_input=value._package.evaluator_input,
        package_id="package-fixture",
        package_sha256="b" * 64,
        activation_manifest_sha256="c" * 64,
    )
    final_session = legacy.FINAL_EXECUTION_SESSION
    value._strategy_equity_observations[final_session] = Decimal(
        "1168510.983845"
    )
    value._terminal_account_observation_adjustment = None
    value._terminal_account_observation_prior_equity = None
    value._terminal_account_observation_equity = None
    return value


def test_v16_profiles_are_exact_v15_extensions_and_v15_is_immutable():
    expected_sha256s = {
        runtime.EXPOSURE_PROFILE_2025_ID: (
            "0ac38709a0666a105e571953bdeb94304439c0c82fe3c3b647edb363b1c0b135"
        ),
        runtime.EXPOSURE_PROFILE_2026_ID: (
            "f23417c65cd80daee2440350ca0598728a896816bd5f5d4412c9352f6ab45f3b"
        ),
    }
    for profile_id, predecessor_id in zip(
        runtime.EXPOSURE_PROFILE_IDS, v15.ACCOUNT_PROFILE_IDS,
    ):
        profile = runtime.require_qqq_order_level_profile(profile_id)
        predecessor = v15.require_qqq_order_level_profile(predecessor_id)
        assert profile["schema"] == runtime.EXPOSURE_PROFILE_SCHEMA
        assert profile["mean_exposure_complement_policy"] == (
            runtime.MEAN_EXPOSURE_COMPLEMENT_POLICY
        )
        assert profile["profile_sha256"] == expected_sha256s[profile_id]
        for record in (profile, predecessor):
            record.pop("profile_sha256")
            record.pop("schema")
            record.pop("profile_id")
        profile.pop("mean_exposure_complement_policy")
        assert profile == predecessor
    assert hashlib.sha256(Path(v15.__file__).read_bytes()).hexdigest() == (
        V15_SOURCE_SHA256
    )
    own_callables = {
        name for name, member in
        runtime.AcceptedRiskQqqOrderLevelV16QcRuntime.__dict__.items()
        if callable(member)
    }
    assert own_callables == {
        "__init__", "_aggregate_record", "on_end_of_algorithm",
    }


def test_r169_real_v15_aggregate_is_corrected_without_other_economic_change():
    value = _r169_real_base_runtime()

    # R169's LEAN process emitted these values under a wider ambient context.
    # Run the unchanged predecessor through that real arithmetic path first.
    with localcontext() as context:
        context.prec = 96
        predecessor = (
            v15.AcceptedRiskQqqOrderLevelV15QcRuntime._aggregate_record(value)
        )
        corrected = value._aggregate_record()

    assert predecessor["mean_gross_exposure"] == R169_MEAN_GROSS_EXPOSURE
    assert predecessor["mean_cash_weight"] == R169_MEAN_CASH_WEIGHT
    with localcontext() as context:
        context.prec = 96
        assert (
            Decimal(predecessor["mean_gross_exposure"])
            + Decimal(predecessor["mean_cash_weight"])
        ) != 1
        assert (
            Decimal(corrected["mean_gross_exposure"])
            + Decimal(corrected["mean_cash_weight"])
        ) == 1
    assert corrected["mean_gross_exposure"] == R169_MEAN_GROSS_EXPOSURE
    assert corrected["mean_cash_weight"] == R169_EXACT_CASH_COMPLEMENT
    assert corrected["schema"] == runtime.EXPOSURE_SUMMARY_SCHEMA
    assert {
        key: value for key, value in corrected.items()
        if key not in {"schema", "mean_cash_weight"}
    } == {
        key: value for key, value in predecessor.items()
        if key not in {"schema", "mean_cash_weight"}
    }


def test_r169_complement_is_independent_of_hostile_ambient_decimal_context():
    source = {
        "schema": v15.ACCOUNT_SUMMARY_SCHEMA,
        "mean_gross_exposure": R169_MEAN_GROSS_EXPOSURE,
        "mean_cash_weight": R169_MEAN_CASH_WEIGHT,
    }
    before = dict(source)
    with localcontext() as context:
        context.prec = 3
        context.traps[Inexact] = True
        corrected = runtime._exact_mean_cash_complement(source)
    assert source == before
    assert corrected == {
        "schema": runtime.EXPOSURE_SUMMARY_SCHEMA,
        "mean_gross_exposure": R169_MEAN_GROSS_EXPOSURE,
        "mean_cash_weight": R169_EXACT_CASH_COMPLEMENT,
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("mean_gross_exposure", 1, "not exact decimal text"),
        ("mean_cash_weight", None, "not exact decimal text"),
        ("mean_gross_exposure", "NaN", "outside zero and one"),
        ("mean_gross_exposure", "-0.0001", "outside zero and one"),
        ("mean_cash_weight", "1.0001", "outside zero and one"),
    ),
)
def test_v16_refuses_invalid_predecessor_exposure(field, value, message):
    source = {
        "schema": v15.ACCOUNT_SUMMARY_SCHEMA,
        "mean_gross_exposure": "0.98",
        "mean_cash_weight": "0.02",
    }
    source[field] = value
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match=message,
    ):
        runtime._exact_mean_cash_complement(source)


def test_v16_refuses_changed_predecessor_schema():
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^order-level V16 predecessor schema changed$",
    ):
        runtime._exact_mean_cash_complement({
            "schema": runtime.EXPOSURE_SUMMARY_SCHEMA,
            "mean_gross_exposure": "0.98",
            "mean_cash_weight": "0.02",
        })


@pytest.mark.parametrize(
    ("gross", "cash"),
    (("0", "1"), ("1", "0")),
)
def test_v16_accepts_closed_unit_boundaries(gross, cash):
    corrected = runtime._exact_mean_cash_complement({
        "schema": v15.ACCOUNT_SUMMARY_SCHEMA,
        "mean_gross_exposure": gross,
        "mean_cash_weight": cash,
    })
    assert corrected["mean_gross_exposure"] == gross
    assert Decimal(corrected["mean_cash_weight"]) + Decimal(gross) == 1


def test_v16_end_callback_binds_profile_digest_and_exact_complement(
    monkeypatch,
):
    value = _end_ready_runtime()
    monkeypatch.setattr(legacy, "MAXIMUM_STATISTIC_BYTES", 8_192)

    value.on_end_of_algorithm()

    stored = value._algorithm.summary_statistics
    aggregate = json.loads(stored[runtime.AGGREGATES_STATISTIC_NAME])
    meta = json.loads(stored[runtime.META_STATISTIC_NAME])
    assert value.completed is True
    assert aggregate["schema"] == runtime.EXPOSURE_SUMMARY_SCHEMA
    with localcontext() as context:
        context.prec = 32_768
        assert (
            Decimal(aggregate["mean_gross_exposure"])
            + Decimal(aggregate["mean_cash_weight"])
        ) == 1
    assert meta["profile_id"] == runtime.EXPOSURE_PROFILE_2026_ID
    assert meta["profile_sha256"] == value._profile["profile_sha256"]
    assert meta["aggregates_sha256"] == legacy._sha(aggregate)
    assert meta["schema"] == "arv2-qqq-order-level-tilt-runtime-meta-v3"


def test_v16_end_callback_transport_refusal_emits_nothing(monkeypatch):
    value = _end_ready_runtime()
    monkeypatch.setattr(legacy, "MAXIMUM_STATISTIC_BYTES", 1)

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^order-level aggregate transport exceeded its exact bound$",
    ):
        value.on_end_of_algorithm()

    assert value.completed is False
    assert value._algorithm.summary_statistics == {}
