import hashlib
import json
from datetime import datetime
from decimal import (
    MAX_EMAX,
    MIN_EMIN,
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    localcontext,
)
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_qc_runtime as legacy,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v17_qc_runtime as v17,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v18_qc_runtime as runtime,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_qqq_order_level_runtime as fixtures,
)


V17_SOURCE_SHA256 = (
    "8049d90e5e04b3d80d61f106441e60e3de98eaf863cd3e569342d6186a6910e5"
)
REFUSAL = runtime.AcceptedRiskQqqOrderLevelQcRuntimeError
FINAL = legacy.FINAL_EXECUTION_SESSION
START = "2026-01-02"


def _runtime(algorithm=None, profile_id=runtime.BOUNDARY_PROFILE_2026_ID):
    algorithm = algorithm or fixtures._Algorithm()
    return runtime.AcceptedRiskQqqOrderLevelV18QcRuntime(
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


def _terminal_ratios(holdings, equity):
    """The inherited V15 ratio arithmetic: 32,768 digits, half-even."""

    context = Context(
        prec=runtime._v15.TERMINAL_ACCOUNT_RATIO_DECIMAL_PRECISION,
        rounding=ROUND_HALF_EVEN,
        Emin=MIN_EMIN,
        Emax=MAX_EMAX,
        capitals=1,
        clamp=0,
    )
    with localcontext(context):
        gross = Decimal(holdings) / Decimal(equity)
        return gross, Decimal(1) - gross


def _terminal_ready(*, holdings, cash, equity, first="1000000", prior="1168510.983845"):
    """A runtime at the terminal snapshot with the given QC account reads."""

    algorithm = fixtures._Algorithm()
    algorithm.portfolio.total_holdings_value = Decimal(holdings)
    algorithm.portfolio.cash = Decimal(cash)
    algorithm.portfolio.total_portfolio_value = Decimal(equity)
    value = _runtime(algorithm)
    value._strategy_equity_observations = {
        START: Decimal(first), FINAL: Decimal(prior),
    }
    value._gross_exposure_observations = {FINAL: Decimal("0.9")}
    value._cash_weight_observations = {FINAL: Decimal("0.1")}
    return value


def test_v18_profiles_are_exact_v17_extensions_and_v17_is_immutable():
    expected_sha256s = {
        runtime.BOUNDARY_PROFILE_2025_ID: (
            "a1b263e741fc952c0e7912a79f782ad9869051e72770f08b8e67e57b350e37d2"
        ),
        runtime.BOUNDARY_PROFILE_2026_ID: (
            "0ad9a2195244d944a56f5747db18e267c7b4202a63d14ae353ed86f939f869eb"
        ),
    }
    for profile_id, predecessor_id in zip(
        runtime.BOUNDARY_PROFILE_IDS, v17.SKIP_PROFILE_IDS,
    ):
        profile = runtime.require_qqq_order_level_profile(profile_id)
        predecessor = v17.require_qqq_order_level_profile(predecessor_id)
        assert profile["schema"] == runtime.BOUNDARY_PROFILE_SCHEMA
        assert profile["terminal_account_composition_policy"] == (
            runtime.TERMINAL_COMPOSITION_POLICY
        )
        assert Decimal(profile["terminal_account_composition_tolerance"]) == (
            Decimal("1E-8")
        )
        assert Decimal(profile["maximum_boundary_observable_equity"]) == (
            Decimal(16_777_216)
        )
        assert profile["decision_skip_policy"] == v17.DECISION_SKIP_POLICY
        assert profile["profile_sha256"] == expected_sha256s[profile_id]
        for record in (profile, predecessor):
            record.pop("profile_sha256")
            record.pop("schema")
            record.pop("profile_id")
        for field in (
            "terminal_account_composition_policy",
            "terminal_account_composition_tolerance",
            "maximum_boundary_observable_equity",
        ):
            profile.pop(field)
        assert profile == predecessor
    assert hashlib.sha256(Path(v17.__file__).read_bytes()).hexdigest() == (
        V17_SOURCE_SHA256
    )
    own_callables = {
        name for name, member in
        runtime.AcceptedRiskQqqOrderLevelV18QcRuntime.__dict__.items()
        if callable(member)
    }
    assert own_callables == {
        "__init__", "_aggregate_record",
        "_replace_terminal_account_observation", "on_end_of_algorithm",
    }
    with pytest.raises(REFUSAL, match="V18 profile is not an exact fixed"):
        runtime.require_qqq_order_level_profile(v17.SKIP_PROFILE_2026_ID)
    with pytest.raises(REFUSAL, match="V18 profile is not an exact fixed"):
        _runtime(profile_id=v17.SKIP_PROFILE_2026_ID)


def test_tolerance_is_below_three_double_roundings_under_the_equity_bound():
    # Below 2**24 dollars a double's unit in the last place is 2**-29; three
    # reads carry at most three units of rounding, which stays under 1E-8.
    ulp = Decimal(2) ** -29
    assert 3 * ulp < runtime.TERMINAL_COMPOSITION_TOLERANCE
    assert runtime.MAXIMUM_BOUNDARY_OBSERVABLE_EQUITY == Decimal(2) ** 24
    # One cent is far outside the tolerance: a real break still refuses.
    assert Decimal("0.01") > runtime.TERMINAL_COMPOSITION_TOLERANCE * 10 ** 5


def test_exact_identity_records_a_zero_residual_and_v15_observations():
    value = _terminal_ready(
        holdings="1120000", cash="48243.410845", equity="1168243.410845",
    )

    value._replace_terminal_account_observation()

    equity = Decimal("1168243.410845")
    gross, cash_weight = _terminal_ratios("1120000", equity)
    assert value._terminal_account_composition_residual == 0
    assert value._strategy_equity_observations[FINAL] == equity
    assert value._gross_exposure_observations[FINAL] == gross
    assert value._cash_weight_observations[FINAL] == cash_weight
    assert value._terminal_account_observation_adjustment == (
        equity - Decimal("1168510.983845")
    )
    assert value._terminal_account_observation_equity == equity
    assert value._portfolio_equity() == equity


@pytest.mark.parametrize(
    "residual_text",
    ("-6E-12", "6E-12", "-1E-8", "1E-8"),
)
def test_boundary_residual_within_tolerance_keeps_engine_equity_authoritative(
    residual_text,
):
    holdings, cash = Decimal("1381054.2127016393"), Decimal("12345.678901234567")
    equity = holdings + cash - Decimal(residual_text)
    value = _terminal_ready(holdings=holdings, cash=cash, equity=equity)

    value._replace_terminal_account_observation()

    assert value._terminal_account_composition_residual == Decimal(
        residual_text
    )
    # Equity is the engine's value, never rebuilt from the components.
    assert value._strategy_equity_observations[FINAL] == equity
    assert value._terminal_account_observation_equity == equity
    gross, cash_weight = _terminal_ratios(holdings, equity)
    assert value._gross_exposure_observations[FINAL] == gross
    assert value._cash_weight_observations[FINAL] == cash_weight


@pytest.mark.parametrize(
    "residual_text",
    ("1.00000001E-8", "-1.00000001E-8", "0.01", "-0.01", "1"),
)
def test_residual_beyond_tolerance_refuses_without_mutation(residual_text):
    holdings, cash = Decimal("1120000"), Decimal("48243.410845")
    equity = holdings + cash - Decimal(residual_text)
    value = _terminal_ready(holdings=holdings, cash=cash, equity=equity)
    before = dict(value._strategy_equity_observations)

    with pytest.raises(
        REFUSAL, match="^order-level terminal account composition changed$",
    ):
        value._replace_terminal_account_observation()

    assert value._strategy_equity_observations == before
    assert value._gross_exposure_observations[FINAL] == Decimal("0.9")
    assert value._terminal_account_observation_adjustment is None
    assert value._terminal_account_observation_equity is None
    assert value._terminal_account_composition_residual is None
    assert value._portfolio_equity() == equity


def test_equity_at_or_above_the_double_bound_refuses_even_when_exact():
    holdings, cash = Decimal("16000000"), Decimal("777216")
    value = _terminal_ready(holdings=holdings, cash=cash, equity=holdings + cash)
    with pytest.raises(
        REFUSAL, match="terminal equity exceeds the double-boundary bound",
    ):
        value._replace_terminal_account_observation()
    assert value._terminal_account_composition_residual is None
    just_below = _terminal_ready(
        holdings="16000000", cash="777215.99", equity="16777215.99",
    )
    just_below._replace_terminal_account_observation()
    assert just_below._terminal_account_composition_residual == 0


def test_residual_check_ignores_the_ambient_decimal_context():
    holdings, cash = Decimal("1381054.2127016393"), Decimal("12345.678901234567")
    equity = holdings + cash - Decimal("6E-12")
    value = _terminal_ready(holdings=holdings, cash=cash, equity=equity)
    with localcontext() as context:
        context.prec = 3
        value._replace_terminal_account_observation()
    assert value._terminal_account_composition_residual == Decimal("6E-12")
    assert value._terminal_account_observation_equity == equity


@pytest.mark.parametrize("mutation", ("start", "missing", "twice"))
def test_inherited_terminal_refusals_are_preserved(mutation):
    value = _terminal_ready(
        holdings="1120000", cash="48243.410845", equity="1168243.410845",
    )
    if mutation == "start":
        value._strategy_equity_observations[START] = Decimal("999999")
        message = "starting account observation changed"
    elif mutation == "missing":
        del value._cash_weight_observations[FINAL]
        message = "terminal account observation is unavailable"
    else:
        value._replace_terminal_account_observation()
        message = "terminal account observation is unavailable"
    with pytest.raises(REFUSAL, match=message):
        value._replace_terminal_account_observation()


def _aggregate_ready(*, residual_text="0"):
    holdings, cash = Decimal("1120000"), Decimal("48243.410845")
    equity = holdings + cash - Decimal(residual_text)
    sessions = (START, FINAL)
    algorithm = fixtures._Algorithm()
    algorithm.portfolio.total_portfolio_value = equity
    algorithm.portfolio.total_holdings_value = holdings
    algorithm.portfolio.cash = cash
    value = _runtime(algorithm)
    value._package = SimpleNamespace(
        evaluator_input=SimpleNamespace(session_axis=sessions),
        package_id="package-fixture",
        package_sha256="b" * 64,
        activation_manifest_sha256="c" * 64,
    )
    value._resolution = fixtures._Resolution({
        "a": fixtures._Symbol("A-SID", "A")
    })
    value._resolved_qqq_weights(
        sessions[0], {"A-SID": Decimal("1")}, constituent_age_sessions=1,
    )
    value._decision_count = 1
    value._decision_sessions = sessions[:1]
    value._submitted_order_count = 1
    value._lifecycle_records = [fixtures._lifecycle_record()]
    value._strategy_equity_observations = {
        sessions[0]: Decimal("1000000"),
        sessions[1]: Decimal("1168510.983845"),
    }
    qqq = ((sessions[0], Decimal("100")), (sessions[1], Decimal("101")))
    value._load_qqq_total_return_observations = (
        lambda expected: qqq if expected == sessions else ()
    )
    value._benchmark_open_observations = {
        sessions[0]: Decimal("100"), sessions[1]: Decimal("100"),
    }
    value._gross_exposure_observations = {
        sessions[0]: Decimal("0"), sessions[1]: Decimal("0.95"),
    }
    value._cash_weight_observations = {
        sessions[0]: Decimal("1"), sessions[1]: Decimal("0.05"),
    }
    return value, equity


@pytest.mark.parametrize("residual_text", ("0", "-6E-12"))
def test_aggregate_reports_the_residual_and_extends_v17_only(residual_text):
    value, equity = _aggregate_ready(residual_text=residual_text)
    value._replace_terminal_account_observation()
    predecessor = v17.AcceptedRiskQqqOrderLevelV17QcRuntime._aggregate_record(
        value
    )
    summary = value._aggregate_record()

    assert predecessor["schema"] == v17.SKIP_SUMMARY_SCHEMA
    assert summary["schema"] == runtime.BOUNDARY_SUMMARY_SCHEMA
    assert Decimal(summary["terminal_account_composition_residual"]) == Decimal(
        residual_text
    )
    assert Decimal(summary["terminal_account_composition_tolerance"]) == (
        Decimal("1E-8")
    )
    assert Decimal(summary["ending_equity"]) == equity
    assert Decimal(summary["terminal_account_observation_equity"]) == equity
    assert summary["run_valid"] is True
    added = {
        "schema", "terminal_account_composition_residual",
        "terminal_account_composition_tolerance",
    }
    assert {k: v for k, v in summary.items() if k not in added} == {
        k: v for k, v in predecessor.items() if k not in added
    }


def test_aggregate_refuses_before_the_terminal_snapshot_or_on_changed_predecessor(
    monkeypatch,
):
    value, _equity = _aggregate_ready()
    with pytest.raises(REFUSAL, match="composition is unreconciled"):
        value._aggregate_record()
    value._replace_terminal_account_observation()
    monkeypatch.setattr(
        v17.AcceptedRiskQqqOrderLevelV17QcRuntime,
        "_aggregate_record",
        lambda _self: {"schema": "other"},
    )
    with pytest.raises(REFUSAL, match="V18 predecessor schema changed"):
        value._aggregate_record()


def _end_ready(residual_text="0"):
    value, equity = _aggregate_ready(residual_text=residual_text)
    value._initialized = True
    value._algorithm.time = datetime.fromisoformat("2026-09-18T00:00:00")
    return value, equity


def test_end_callback_binds_v18_profile_and_emits_the_residual(monkeypatch):
    value, equity = _end_ready("-6E-12")
    monkeypatch.setattr(legacy, "MAXIMUM_STATISTIC_BYTES", 8_192)

    value.on_end_of_algorithm()

    stored = value._algorithm.summary_statistics
    aggregate = json.loads(stored[runtime.AGGREGATES_STATISTIC_NAME])
    meta = json.loads(stored[runtime.META_STATISTIC_NAME])
    assert value.completed is True
    assert aggregate["schema"] == runtime.BOUNDARY_SUMMARY_SCHEMA
    assert Decimal(aggregate["terminal_account_composition_residual"]) == (
        Decimal("-6E-12")
    )
    assert Decimal(aggregate["ending_equity"]) == equity
    assert meta["profile_id"] == runtime.BOUNDARY_PROFILE_2026_ID
    assert meta["profile_sha256"] == value._profile["profile_sha256"]
    assert meta["aggregates_sha256"] == legacy._sha(aggregate)
    assert meta["trading"] is False


def test_end_callback_refuses_a_real_composition_break_before_output(
    monkeypatch,
):
    value, _equity = _end_ready("0.01")
    monkeypatch.setattr(legacy, "MAXIMUM_STATISTIC_BYTES", 8_192)
    with pytest.raises(REFUSAL, match="terminal account composition changed"):
        value.on_end_of_algorithm()
    assert value.completed is False
    assert value._algorithm.summary_statistics == {}


def test_end_callback_transport_refusal_emits_nothing(monkeypatch):
    value, _equity = _end_ready()
    monkeypatch.setattr(legacy, "MAXIMUM_STATISTIC_BYTES", 1)
    with pytest.raises(
        REFUSAL, match="^order-level aggregate transport exceeded its exact bound$",
    ):
        value.on_end_of_algorithm()
    assert value.completed is False
    assert value._algorithm.summary_statistics == {}


@pytest.mark.parametrize("state", ("pending", "completed", "clock", "schedule"))
def test_end_callback_inherited_gates_remain(state, monkeypatch):
    value, _equity = _end_ready()
    monkeypatch.setattr(legacy, "MAXIMUM_STATISTIC_BYTES", 8_192)
    if state == "pending":
        value._pending_preopen = ("2026-09-17", None)
        message = "pending preopen submission remained at end"
    elif state == "completed":
        value._completed = True
        message = "end callback escaped runtime state"
    elif state == "clock":
        value._algorithm.time = datetime.fromisoformat("2026-09-18T00:00:01")
        message = "ended outside the exact final clock"
    else:
        value._decision_sessions = (START, FINAL)
        message = "decision schedule did not complete"
    with pytest.raises(REFUSAL, match=message):
        value.on_end_of_algorithm()
    assert value._algorithm.summary_statistics == {}
