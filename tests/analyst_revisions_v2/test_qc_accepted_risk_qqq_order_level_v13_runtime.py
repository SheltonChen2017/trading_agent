import hashlib
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_qc_runtime as legacy,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v12_qc_runtime as v12,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v13_qc_runtime as runtime,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_qqq_order_level_runtime as fixtures,
)


V12_SOURCE_SHA256 = (
    "fd8913e4f9791f512796ab34ede39eafba337de6b76012de48f272cb613be760"
)


def _runtime(algorithm=None, profile_id=runtime.ROLLOVER_PROFILE_2026_ID):
    algorithm = algorithm or fixtures._Algorithm()
    return runtime.AcceptedRiskQqqOrderLevelV13QcRuntime(
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


def _end_ready(callback_time):
    algorithm = fixtures._Algorithm()
    algorithm.time = callback_time
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
        "schema": v12.FORCED_EXIT_SUMMARY_SCHEMA,
        "run_valid": True,
    }
    value._aggregate_record = lambda: aggregate
    return value, algorithm, aggregate


def test_v13_profiles_are_exact_v12_extensions_and_bind_clock_policy():
    assert runtime.ROLLOVER_PROFILE_IDS == (
        "arv2-qqq-order-level-tilt-2025-cutoff-v13",
        "arv2-qqq-order-level-tilt-2026-cutoff-v13",
    )
    expected = {
        runtime.ROLLOVER_PROFILE_2025_ID: (
            "af9956518f5bb59512c8519766ffa018fee790a502cdb40279d69c32e4a86c4a"
        ),
        runtime.ROLLOVER_PROFILE_2026_ID: (
            "1f2778f9e98ffab7c2030b5cab8080248b2d561420cc4c9d769de89fa46e6fa1"
        ),
    }
    v12_ids = (
        v12.FORCED_EXIT_PROFILE_2025_ID,
        v12.FORCED_EXIT_PROFILE_2026_ID,
    )
    for profile_id, v12_id in zip(runtime.ROLLOVER_PROFILE_IDS, v12_ids):
        profile = runtime.require_qqq_order_level_profile(profile_id)
        predecessor = v12.require_qqq_order_level_profile(v12_id)
        assert profile["schema"] == runtime.ROLLOVER_PROFILE_SCHEMA
        assert profile["profile_sha256"] == expected[profile_id]
        assert profile["qc_end_callback_clock_policy"] == (
            "final_execution_session_or_exact_next_calendar_day_midnight"
        )
        for record in (profile, predecessor):
            record.pop("profile_sha256")
            record.pop("schema")
            record.pop("profile_id")
        profile.pop("qc_end_callback_clock_policy")
        assert profile == predecessor
        assert runtime.expected_custom_summary_statistic_names(profile_id) == (
            legacy.AGGREGATES_STATISTIC_NAME,
            legacy.META_STATISTIC_NAME,
        )


def test_v12_source_is_byte_identical_and_v13_inherits_v12_economics():
    assert hashlib.sha256(Path(v12.__file__).read_bytes()).hexdigest() == (
        V12_SOURCE_SHA256
    )
    assert issubclass(
        runtime.AcceptedRiskQqqOrderLevelV13QcRuntime,
        v12.AcceptedRiskQqqOrderLevelV12QcRuntime,
    )
    for method in (
        "_aggregate_record",
        "_record_forced_delisting_exit",
        "on_before_open",
        "on_data",
        "on_order_event",
    ):
        assert (
            getattr(runtime.AcceptedRiskQqqOrderLevelV13QcRuntime, method)
            is getattr(v12.AcceptedRiskQqqOrderLevelV12QcRuntime, method)
        )


@pytest.mark.parametrize(
    "callback_time",
    (
        datetime.fromisoformat("2026-09-17T00:00:00"),
        datetime.fromisoformat("2026-09-17T16:00:00"),
        datetime.fromisoformat("2026-09-18T00:00:00"),
    ),
)
def test_v13_end_callback_accepts_only_final_session_or_exact_rollover_midnight(
    callback_time,
):
    value, algorithm, aggregate = _end_ready(callback_time)

    value.on_end_of_algorithm()

    assert tuple(sorted(algorithm.summary_statistics)) == (
        legacy.AGGREGATES_STATISTIC_NAME,
        legacy.META_STATISTIC_NAME,
    )
    assert json.loads(
        algorithm.summary_statistics[legacy.AGGREGATES_STATISTIC_NAME]
    ) == aggregate
    meta = json.loads(algorithm.summary_statistics[legacy.META_STATISTIC_NAME])
    assert meta["schema"] == "arv2-qqq-order-level-tilt-runtime-meta-v2"
    assert meta["profile_id"] == runtime.ROLLOVER_PROFILE_2026_ID
    assert meta["profile_sha256"] == value._profile["profile_sha256"]
    assert value._completed is True


@pytest.mark.parametrize(
    "callback_time",
    (
        datetime.fromisoformat("2026-09-16T23:59:59.999999"),
        datetime.fromisoformat("2026-09-18T00:00:00.000001"),
        datetime.fromisoformat("2026-09-18T00:00:01"),
        datetime.fromisoformat("2026-09-18T00:01:00"),
        datetime.fromisoformat("2026-09-18T16:00:00"),
        datetime.fromisoformat("2026-09-19T00:00:00"),
    ),
)
def test_v13_end_callback_refuses_every_other_clock_atomically(callback_time):
    value, algorithm, _aggregate = _end_ready(callback_time)

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^order-level backtest ended outside the exact final clock$",
    ):
        value.on_end_of_algorithm()

    assert algorithm.summary_statistics == {}
    assert value._completed is False


@pytest.mark.parametrize(
    ("initialized", "completed"),
    ((False, False), (True, True)),
)
def test_v13_end_callback_refuses_uninitialized_or_completed_state_before_output(
    initialized, completed,
):
    value, algorithm, _aggregate = _end_ready(
        datetime.fromisoformat("2026-09-18T00:00:00")
    )
    value._initialized = initialized
    value._completed = completed

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^order-level end callback escaped runtime state$",
    ):
        value.on_end_of_algorithm()

    assert algorithm.summary_statistics == {}


def test_v13_end_callback_refuses_pending_preopen_plan_before_output():
    value, algorithm, _aggregate = _end_ready(
        datetime.fromisoformat("2026-09-18T00:00:00")
    )
    value._pending_preopen = ("2026-09-17", object())

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^order-level pending preopen submission remained at end$",
    ):
        value.on_end_of_algorithm()

    assert algorithm.summary_statistics == {}


def test_v13_end_callback_refuses_incomplete_decision_schedule_before_output():
    value, algorithm, _aggregate = _end_ready(
        datetime.fromisoformat("2026-09-18T00:00:00")
    )
    value._decision_sessions = ("2026-09-16",)

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^order-level decision schedule did not complete$",
    ):
        value.on_end_of_algorithm()

    assert algorithm.summary_statistics == {}


def test_v13_end_callback_refuses_oversized_aggregate_before_output():
    value, algorithm, _aggregate = _end_ready(
        datetime.fromisoformat("2026-09-18T00:00:00")
    )
    value._aggregate_record = lambda: {"oversized": "x" * 8_192}

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^order-level aggregate transport exceeded its exact bound$",
    ):
        value.on_end_of_algorithm()

    assert algorithm.summary_statistics == {}
    assert value._completed is False


def test_v13_unknown_profile_refuses_before_v12_initialization():
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^QQQ order-level V13 profile is not an exact fixed profile$",
    ):
        _runtime(profile_id=v12.FORCED_EXIT_PROFILE_2026_ID)
