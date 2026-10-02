import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_order_level_universe_benchmark as universe_benchmark,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_qc_runtime as legacy,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v19_qc_runtime as v19,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_spy_order_level_v1_qc_runtime as runtime,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_qqq_order_level_runtime as fixtures,
)


REFUSAL = runtime.AcceptedRiskSpyOrderLevelQcRuntimeError
START = "2026-01-02"
FINAL = legacy.FINAL_EXECUTION_SESSION


def _runtime(algorithm=None):
    algorithm = algorithm or fixtures._Algorithm()
    spy = fixtures._Symbol("SPY-SID", "SPY")
    return runtime.AcceptedRiskSpyOrderLevelV1QcRuntime(
        algorithm,
        activation_manifest_key="arv2/x/transport-manifest.json",
        activation_manifest_sha256="a" * 64,
        activation_manifest_byte_count=1,
        profile_id=runtime.SUCCESSOR_PROFILE_2026_ID,
        authority_benchmark_symbol=spy,
        spy_benchmark_symbol=spy,
        spy_constituent_universe=SimpleNamespace(
            symbol=fixtures._Symbol("SPYU-SID")
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


def _aggregate_ready(*, replace_terminal=True):
    sessions = (START, FINAL)
    algorithm = fixtures._Algorithm()
    algorithm.portfolio.total_portfolio_value = Decimal("1168243.410845")
    algorithm.portfolio.total_holdings_value = Decimal("1120000")
    algorithm.portfolio.cash = Decimal("48243.410845")
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
        START,
        {"A-SID": Decimal("1")},
        constituent_age_sessions=1,
    )
    value._decision_count = 1
    value._decision_sessions = (START,)
    value._decision_set = frozenset({START})
    value._executed_decision_sessions = [START]
    value._submitted_order_count = 1
    value._lifecycle_records = [fixtures._lifecycle_record()]
    value._strategy_equity_observations = {
        START: Decimal("1000000"),
        FINAL: Decimal("1168510.983845"),
    }
    benchmark = (
        (START, Decimal("100")),
        (FINAL, Decimal("101")),
    )
    value._load_spy_total_return_observations = (
        lambda expected: benchmark if expected == sessions else ()
    )
    value._benchmark_observations = dict(benchmark)
    value._benchmark_open_observations = {
        START: Decimal("100"),
        FINAL: Decimal("100"),
    }
    value._gross_exposure_observations = {
        START: Decimal("0"),
        FINAL: Decimal("0.95"),
    }
    value._cash_weight_observations = {
        START: Decimal("1"),
        FINAL: Decimal("0.05"),
    }
    if replace_terminal:
        value._replace_terminal_account_observation()
    return value


def _canonical_text(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def test_profiles_are_spy_only_extensions_of_immutable_v19_mechanics():
    expected_sha256s = {
        runtime.SUCCESSOR_PROFILE_2025_ID: (
            "207256f60903bf96de5c95d1e7833905b8b423e4d13e130232ae4d579bf6d6e9"
        ),
        runtime.SUCCESSOR_PROFILE_2026_ID: (
            "7943e61bb47b25977ce6a21009030f920df387de3be2fec75ff2effeea4dd454"
        ),
    }
    for profile_id in runtime.SUCCESSOR_PROFILE_IDS:
        profile = runtime.require_spy_order_level_profile(profile_id)
        assert profile["schema"] == runtime.SUCCESSOR_PROFILE_SCHEMA
        assert profile["profile_sha256"] == expected_sha256s[profile_id]
        assert profile["universe_proxy_ticker"] == "SPY"
        assert profile["universe_scope_disclaimer"] == (
            "SPY_holdings_proxy_not_official_SP500_index_membership"
        )
        assert profile["spy_proxy_security_id"] == (
            runtime.SPY_PROXY_SECURITY_ID
        )
        assert profile["maximum_custom_statistic_bytes_each"] == 16_384
        assert profile["mechanics_parent_profile_sha256"] in {
            v19.require_qqq_order_level_profile(parent)["profile_sha256"]
            for parent in v19.SUCCESSOR_PROFILE_IDS
        }
        assert "qqq" not in _canonical_text(profile).lower()
        assert runtime.expected_custom_summary_statistic_names(profile_id) == (
            runtime.AGGREGATES_STATISTIC_NAME,
            runtime.META_STATISTIC_NAME,
        )


def test_public_constructor_refuses_predecessor_universe_kwargs():
    with pytest.raises(
        REFUSAL, match="received predecessor universe kwargs",
    ):
        runtime.AcceptedRiskSpyOrderLevelV1QcRuntime(
            fixtures._Algorithm(),
            profile_id=runtime.SUCCESSOR_PROFILE_2026_ID,
            spy_benchmark_symbol=fixtures._Symbol("SPY-SID", "SPY"),
            spy_constituent_universe=SimpleNamespace(
                symbol=fixtures._Symbol("SPYU-SID")
            ),
            qqq_benchmark_symbol=fixtures._Symbol("OTHER-SID"),
        )


def test_spy_coverage_uses_generic_helper_and_confines_proxy_translation(
    monkeypatch,
):
    value = _runtime()
    value._resolution = fixtures._Resolution({
        "a": fixtures._Symbol("A-SID", "A")
    })
    calls = []
    original = universe_benchmark.resolved_universe_holdings_weight_core

    def observed(*args, **kwargs):
        calls.append(kwargs.copy())
        return original(*args, **kwargs)

    monkeypatch.setattr(
        universe_benchmark,
        "resolved_universe_holdings_weight_core",
        observed,
    )
    measures = value._resolved_qqq_weights(
        START,
        {"A-SID": Decimal("0.86"), "B-SID": Decimal("0.14")},
        constituent_age_sessions=1,
    )

    assert calls[0]["ticker"] == "SPY"
    assert calls[0]["proxy_record_prefix"] == "spy"
    assert calls[0]["proxy_security_id"] == runtime.SPY_PROXY_SECURITY_ID
    assert measures == {
        "a": Decimal("0.86"),
        legacy._PROXY_ID: Decimal("0.14"),
    }
    assert runtime.SPY_PROXY_SECURITY_ID not in measures
    assert value._spy_pit_coverage_records[0][
        "spy_proxy_reported_weight"
    ] == "0.14"
    assert "qqq" not in _canonical_text(
        value._spy_pit_coverage_records
    ).lower()
    assert value._pit_coverage_records[0][
        "qqq_proxy_reported_weight"
    ] == "0.14"


def test_aggregate_rebinds_every_external_semantic_to_spy():
    value = _aggregate_ready()

    summary = value._aggregate_record()

    assert summary["schema"] == runtime.SUCCESSOR_SUMMARY_SCHEMA
    assert summary["SPY_total_return"] == "0.00882"
    assert summary["SPY_first_execution_session"] == FINAL
    assert summary["SPY_observation_count"] == 2
    assert summary["strategy_minus_SPY_total_return"] == (
        "0.159423410845"
    )
    assert summary["spy_proxy_overlap_disclosure"] == (
        runtime.SPY_PROXY_OVERLAP_DISCLOSURE
    )
    assert summary["internal_predecessor_proxy_token_emitted"] is False
    assert "qqq" not in _canonical_text(summary).lower()


def test_spy_benchmark_entry_follows_first_actually_executed_decision():
    first_scheduled = START
    first_executed = "2026-01-05"
    sessions = (first_scheduled, first_executed, FINAL)
    value = _aggregate_ready()
    value._package.evaluator_input.session_axis = sessions
    value._pit_coverage_records = []
    value._spy_pit_coverage_records = []
    value._resolved_qqq_weights(
        first_executed,
        {"A-SID": Decimal("1")},
        constituent_age_sessions=1,
    )
    value._decision_count = 1
    value._decision_sessions = (first_scheduled, first_executed)
    value._decision_set = frozenset(value._decision_sessions)
    value._executed_decision_sessions = [first_executed]
    value._record_skipped_decision({
        "decision_session": first_scheduled,
        "reason": v19._v17.STALE_SNAPSHOT_SKIP_REASON,
        "expected_snapshot_session": "2025-12-31",
        "served_snapshot_session": "2025-12-30",
        "served_snapshot_age_sessions": 2,
    })
    value._strategy_equity_observations[first_executed] = Decimal("1000000")
    value._gross_exposure_observations[first_executed] = Decimal("0")
    value._cash_weight_observations[first_executed] = Decimal("1")
    benchmark = (
        (first_scheduled, Decimal("100")),
        (first_executed, Decimal("101")),
        (FINAL, Decimal("102")),
    )
    value._load_spy_total_return_observations = (
        lambda expected: benchmark if expected == sessions else ()
    )
    value._benchmark_observations = dict(benchmark)
    value._benchmark_open_observations = {
        first_scheduled: Decimal("100"),
        first_executed: Decimal("100"),
        FINAL: Decimal("101"),
    }

    summary = value._aggregate_record()

    assert summary["first_scheduled_decision_session"] == first_scheduled
    assert summary["first_executed_decision_session"] == first_executed
    assert summary["first_scheduled_decision_executed"] is False
    assert summary["SPY_first_execution_session"] == FINAL


def test_end_callback_emits_only_spy_meta_and_aggregate(monkeypatch):
    value = _aggregate_ready(replace_terminal=False)
    value._initialized = True
    value._algorithm.time = datetime.fromisoformat("2026-09-18T00:00:00")
    monkeypatch.setattr(legacy, "MAXIMUM_STATISTIC_BYTES", 16_384)

    value.on_end_of_algorithm()

    assert tuple(sorted(value._algorithm.summary_statistics)) == (
        runtime.AGGREGATES_STATISTIC_NAME,
        runtime.META_STATISTIC_NAME,
    )
    meta = json.loads(
        value._algorithm.summary_statistics[runtime.META_STATISTIC_NAME]
    )
    aggregate = json.loads(
        value._algorithm.summary_statistics[
            runtime.AGGREGATES_STATISTIC_NAME
        ]
    )
    assert meta["schema"] == runtime.SUCCESSOR_META_SCHEMA
    assert meta["universe_proxy_ticker"] == "SPY"
    assert meta["aggregates_sha256"] == legacy._sha(aggregate)
    assert aggregate["schema"] == runtime.SUCCESSOR_SUMMARY_SCHEMA
    assert "qqq" not in _canonical_text(meta).lower()
    assert "qqq" not in _canonical_text(aggregate).lower()
    assert value.completed is True
