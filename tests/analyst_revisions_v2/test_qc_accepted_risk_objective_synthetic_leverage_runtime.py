import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_market_cap_stock_portfolio_evaluator as market,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_objective_synthetic_leverage_evaluator as evaluator,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_objective_synthetic_leverage_qc_runtime as runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_rating_evaluator as rating,
)


RUNTIME_PATH = (
    Path(__file__).parents[2]
    / "research"
    / "analyst_revisions_v2_qc"
    / "accepted_risk_objective_synthetic_leverage_qc_runtime.py"
)


class _Algorithm:
    def __init__(self):
        self.summary = {}

    def set_summary_statistic(self, key, value):
        self.summary[key] = value


def _driver(profile_id=evaluator.QQQ_2021_2025_V3_PROFILE_ID):
    ticker = evaluator.require_profile(profile_id)["universe_proxy_ticker"]
    return runtime.AcceptedRiskObjectiveSyntheticLeverageQcDriver(
        _Algorithm(),
        activation_manifest_key="arv2/test/transport-manifest.json",
        activation_manifest_sha256="a" * 64,
        activation_manifest_byte_count=1,
        benchmark_symbol=object(),
        trade_bar_type=object,
        daily_resolution=object(),
        total_return_normalization=object(),
        evaluation_profile_id=profile_id,
        fundamental_universe=object(),
        constituent_universes={ticker: object()},
    )


def test_wrapper_is_compact_standalone_and_adds_no_capability_import():
    source = RUNTIME_PATH.read_bytes()
    text = source.decode("ascii")
    assert len(source) < 60_000
    tree = ast.parse(text)
    direct = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name.startswith("accepted_risk_")
    }
    assert direct == {
        "accepted_risk_market_cap_stock_portfolio_evaluator",
        "accepted_risk_market_cap_stock_portfolio_qc_runtime",
        "accepted_risk_objective_synthetic_leverage_evaluator",
    }
    assert "AlgorithmImports" not in text
    assert "requests" not in text
    assert "urllib" not in text
    assert "MarketOrder" not in text
    assert "SetHoldings" not in text
    compile(text, RUNTIME_PATH.name, "exec")
    compile("QC_PRELUDE_SENTINEL = True\n" + text, RUNTIME_PATH.name, "exec")


def test_exact_leverage_to_base_profile_mapping_and_tickers():
    expected = {
        evaluator.QQQ_2021_2025_V3_PROFILE_ID: (
            market.QQQ_2021_2025_V2_PROFILE_ID,
            ("QQQ",),
        ),
        evaluator.SPY_2021_2025_V3_PROFILE_ID: (
            market.SPY_2021_2025_V2_PROFILE_ID,
            ("SPY",),
        ),
    }
    assert runtime.PROFILE_IDS == tuple(expected)
    for profile_id, (base_profile_id, tickers) in expected.items():
        assert runtime.base_market_cap_profile_id_for_profile(
            profile_id
        ) == base_profile_id
        assert runtime.constituent_etf_tickers_for_profile(
            profile_id
        ) == tickers
        driver = _driver(profile_id)
        assert driver._leverage_profile_id == profile_id
        assert driver._evaluation_profile_id == base_profile_id
        assert driver._base_profile_id == base_profile_id
    with pytest.raises(
        evaluator.ObjectiveSyntheticLeverageEvaluationError,
        match="exact fixed profile",
    ):
        runtime.base_market_cap_profile_id_for_profile("unknown")


def test_driver_rejects_constituent_inventory_for_other_base_profile():
    with pytest.raises(
        runtime.AcceptedRiskObjectiveSyntheticLeverageQcRuntimeError,
        match="ETF universe inventory changed",
    ):
        runtime.AcceptedRiskObjectiveSyntheticLeverageQcDriver(
            _Algorithm(),
            activation_manifest_key="arv2/test/transport-manifest.json",
            activation_manifest_sha256="a" * 64,
            activation_manifest_byte_count=1,
            benchmark_symbol=object(),
            trade_bar_type=object,
            daily_resolution=object(),
            total_return_normalization=object(),
            evaluation_profile_id=evaluator.QQQ_2021_2025_V3_PROFILE_ID,
            fundamental_universe=object(),
            constituent_universes={"SPY": object()},
        )


@pytest.mark.parametrize("profile_id", evaluator.PROFILE_IDS)
def test_evaluator_initialization_dispatches_leverage_profile_and_base_maps(
    monkeypatch, profile_id
):
    driver = _driver(profile_id)
    source_input = object()
    maps = {"2021-01-04": {"security": object()}}
    driver._package = SimpleNamespace(
        evaluator_input=source_input,
        package_id="arv2-package",
        package_sha256="b" * 64,
    )
    driver._pit_loader = SimpleNamespace(
        require_completed_market_caps=lambda: maps
    )
    driver._named_refusals = ("named-refusal",)
    captured = {}

    class _Runtime:
        def __init__(self, value, **kwargs):
            captured["value"] = value
            captured.update(kwargs)

    monkeypatch.setattr(
        runtime.leverage_evaluator,
        "ObjectiveSyntheticLeverageEvaluationRuntime",
        _Runtime,
    )
    driver._initialize_evaluator()
    assert type(driver._runtime) is _Runtime
    assert captured == {
        "value": source_input,
        "profile_id": profile_id,
        "package_id": "arv2-package",
        "package_sha256": "b" * 64,
        "named_figi_resolution_refusals": ("named-refusal",),
        "eligibility_market_caps_by_decision_session": maps,
    }


@pytest.mark.parametrize("profile_id", evaluator.PROFILE_IDS)
def test_completed_emission_is_fresh_bounded_aggregate_only_metadata(
    profile_id,
):
    driver = _driver(profile_id)
    expected_evaluator_names = (
        evaluator.expected_custom_summary_statistic_names(profile_id)
    )

    class _CompletedRuntime:
        phase = rating.RuntimePhase.COMPLETED

        @staticmethod
        def custom_summary_statistics():
            return {name: "{}" for name in expected_evaluator_names}

    driver._runtime = _CompletedRuntime()
    driver._package = SimpleNamespace(
        package_id="arv2-test-package",
        package_sha256="b" * 64,
        activation_manifest_sha256="c" * 64,
    )
    driver._resolution = SimpleNamespace(
        resolution_id="arv2-test-resolution",
        resolution_sha256="d" * 64,
        resolved_count=101,
        named_refusal_count=2,
    )
    driver._pit_loader = SimpleNamespace(
        history_call_count=52,
        fetched_source_row_count=123_456,
        eligible_score_bearing_count=1_000,
        covered_count=950,
        uncovered_count=50,
    )
    driver._runtime_slice_count = 77

    driver.emit_completed_summary()
    assert tuple(sorted(driver._algorithm.summary)) == (
        runtime.expected_custom_summary_statistic_names(profile_id)
    )
    assert all(
        len(key) <= 64 and len(value) <= 4096
        for key, value in driver._algorithm.summary.items()
    )
    meta = json.loads(
        driver._algorithm.summary[runtime.RUNTIME_META_STATISTIC]
    )
    profile = evaluator.require_profile(profile_id)
    assert meta == {
        "schema": runtime.RUNTIME_META_SCHEMA,
        "status": runtime.RUNTIME_COMPLETED_STATUS,
        "package_id": "arv2-test-package",
        "package_sha256": "b" * 64,
        "activation_manifest_sha256": "c" * 64,
        "symbol_resolution_id": "arv2-test-resolution",
        "symbol_resolution_sha256": "d" * 64,
        "resolved_security_count": 101,
        "named_security_refusal_count": 2,
        "evaluation_profile_id": profile_id,
        "evaluation_profile_sha256": profile["profile_sha256"],
        "base_market_cap_profile_id": profile["base_profile_id"],
        "base_market_cap_profile_sha256": profile[
            "base_profile_sha256"
        ],
        "runtime_slice_count": 77,
        "point_in_time_history_call_count": 52,
        "point_in_time_fetched_source_row_count": 123_456,
        "point_in_time_eligible_score_bearing_count": 1_000,
        "point_in_time_market_cap_covered_count": 950,
        "point_in_time_market_cap_uncovered_count": 50,
        "leverage_factors": [2, 3],
        "scenario_ids": [
            evaluator.PRIMARY_SCENARIO_ID,
            evaluator.ADVERSE_SCENARIO_ID,
        ],
        "result_transport": "aggregate_only_custom_summary_statistics",
        "host_object_store_export_required": False,
        "preliminary": True,
        "point_in_time": True,
        "formal": False,
        "control_residualized": False,
        "economic_portfolio": True,
        "etf_or_leverage": True,
        "synthetic_leverage": True,
        "margin_calls_modeled": False,
        "borrow_availability_modeled": False,
        "deployment": False,
        "orders": False,
        "trading": False,
    }
    payload = json.dumps(driver._algorithm.summary, sort_keys=True)
    assert "security_id" not in payload
    assert "market_cap_values" not in payload
    assert driver.require_completed_at_end() is True


def test_result_names_are_exact_and_include_runtime_meta_once():
    for profile_id in runtime.PROFILE_IDS:
        expected = tuple(
            sorted(
                (
                    *evaluator.expected_custom_summary_statistic_names(
                        profile_id
                    ),
                    runtime.RUNTIME_META_STATISTIC,
                )
            )
        )
        names = runtime.expected_custom_summary_statistic_names(profile_id)
        assert names == expected
        assert names.count(runtime.RUNTIME_META_STATISTIC) == 1
