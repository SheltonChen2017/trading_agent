import hashlib
import json
from decimal import Decimal, ROUND_DOWN, ROUND_UP, localcontext
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_qc_runtime as legacy,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v13_qc_runtime as v13,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_qqq_order_level_v14_qc_runtime as runtime,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_qqq_order_level_runtime as fixtures,
)


V13_SOURCE_SHA256 = (
    "c7a12b200ac7c5e3bca360c1751464442c8eb5ac535292a1df13cb39580ca6c5"
)


def _runtime(algorithm=None, profile_id=runtime.DIAGNOSTIC_PROFILE_2026_ID):
    algorithm = algorithm or fixtures._Algorithm()
    return runtime.AcceptedRiskQqqOrderLevelV14QcRuntime(
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


def _summary(*, skipped=0, run_valid=True):
    return {
        "schema": "arv2-qqq-order-level-tilt-summary-v8",
        "mean_resolved_constituent_weight_ratio": (
            "0.873456789012345678901234567890123456789012345678901234567890"
            "1234567890123456789012345678901234567890"
        ),
        "minimum_resolved_constituent_weight_ratio": (
            "0.844784478447844784478447844784478447844784478447844784478447"
            "8447844784478447844784478447844784478448"
        ),
        "mean_qqq_proxy_constituent_weight_ratio": "0.1265432109876543210987654321",
        "minimum_qqq_proxy_constituent_weight_ratio": "0.09",
        "maximum_qqq_proxy_constituent_weight_ratio": "0.1552155215521552155215521552",
        "skipped_unpriced_decision_count": skipped,
        "run_valid": run_valid,
    }


def _coverage_records():
    return [
        {
            "resolved_constituent_weight_ratio": (
                "0.910000000000000000000000000000000000000000000000000000000001"
            )
        },
        {
            "resolved_constituent_weight_ratio": (
                "0.844784478447844784478447844784478447844784478447844784478447"
                "8447844784478447844784478447844784478448"
            )
        },
    ]


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
        "schema": runtime.DIAGNOSTIC_SUMMARY_SCHEMA,
        "run_valid": False,
    }
    value._aggregate_record = lambda: aggregate
    return value, algorithm, aggregate


def test_v14_profiles_are_exact_v13_extensions_with_fresh_exact_policies():
    assert runtime.DIAGNOSTIC_PROFILE_IDS == (
        "arv2-qqq-order-level-tilt-2025-cutoff-v14",
        "arv2-qqq-order-level-tilt-2026-cutoff-v14",
    )
    expected = {
        runtime.DIAGNOSTIC_PROFILE_2025_ID: (
            "d1367ac6dd6a7446632b381496ff02be8e602f02373b31ff6c81e9d704298200"
        ),
        runtime.DIAGNOSTIC_PROFILE_2026_ID: (
            "bfb77eacdaddb8566b649165eb4986ca038658bbc23d5eb95641f4cea13d0776"
        ),
    }
    for profile_id, predecessor_id in zip(
        runtime.DIAGNOSTIC_PROFILE_IDS, v13.ROLLOVER_PROFILE_IDS,
    ):
        profile = runtime.require_qqq_order_level_profile(profile_id)
        predecessor = v13.require_qqq_order_level_profile(predecessor_id)
        assert profile["profile_sha256"] == expected[profile_id]
        assert profile["schema"] == runtime.DIAGNOSTIC_PROFILE_SCHEMA
        assert profile["qqq_proxy_complement_policy"] == (
            runtime.EXACT_COMPLEMENT_POLICY
        )
        assert profile["skipped_unpriced_decision_evidence_policy"] == (
            runtime.SKIPPED_UNPRICED_EVIDENCE_POLICY
        )
        assert profile["maximum_retained_skipped_unpriced_decisions"] == 4
        assert (
            profile["maximum_retained_missing_security_hashes_per_decision"]
            == 4
        )
        for record in (profile, predecessor):
            record.pop("profile_sha256")
            record.pop("schema")
            record.pop("profile_id")
        for name in (
            "qqq_proxy_complement_policy",
            "skipped_unpriced_decision_evidence_policy",
            "maximum_retained_skipped_unpriced_decisions",
            "maximum_retained_missing_security_hashes_per_decision",
        ):
            profile.pop(name)
        assert profile == predecessor
        assert runtime.expected_custom_summary_statistic_names(profile_id) == (
            legacy.AGGREGATES_STATISTIC_NAME,
            legacy.META_STATISTIC_NAME,
        )


def test_v13_source_is_immutable_and_v14_changes_only_named_runtime_paths():
    assert hashlib.sha256(Path(v13.__file__).read_bytes()).hexdigest() == (
        V13_SOURCE_SHA256
    )
    assert issubclass(
        runtime.AcceptedRiskQqqOrderLevelV14QcRuntime,
        v13.AcceptedRiskQqqOrderLevelV13QcRuntime,
    )
    for method in (
        "_record_forced_delisting_exit",
        "on_before_open",
        "on_data",
        "on_order_event",
    ):
        assert (
            getattr(runtime.AcceptedRiskQqqOrderLevelV14QcRuntime, method)
            is getattr(v13.AcceptedRiskQqqOrderLevelV13QcRuntime, method)
        )


def test_exact_proxy_complements_ignore_the_ambient_decimal_context(monkeypatch):
    predecessor = _summary()
    monkeypatch.setattr(
        v13.AcceptedRiskQqqOrderLevelV13QcRuntime,
        "_aggregate_record",
        lambda _self: dict(predecessor),
    )
    value = _runtime()
    value._pit_coverage_records = _coverage_records()

    with localcontext() as context:
        context.prec = 6
        context.rounding = ROUND_UP
        low_precision = value._aggregate_record()
    with localcontext() as context:
        context.prec = 211
        context.rounding = ROUND_DOWN
        high_precision = value._aggregate_record()

    assert low_precision == high_precision
    assert low_precision["schema"] == runtime.DIAGNOSTIC_SUMMARY_SCHEMA
    assert low_precision["mean_qqq_proxy_constituent_weight_ratio"] == (
        "0.126543210987654321098765432109876543210987654321098765432109"
        "876543210987654321098765432109876543211"
    )
    assert low_precision["minimum_qqq_proxy_constituent_weight_ratio"] == (
        "0.089999999999999999999999999999999999999999999999999999999999"
    )
    assert low_precision["maximum_qqq_proxy_constituent_weight_ratio"] == (
        "0.155215521552155215521552155215521552155215521552155215521552"
        "1552155215521552155215521552155215521552"
    )
    with localcontext() as context:
        context.prec = 1_000
        assert (
            Decimal(low_precision["mean_qqq_proxy_constituent_weight_ratio"])
            + Decimal(predecessor["mean_resolved_constituent_weight_ratio"])
            == 1
        )
        assert (
            Decimal(low_precision["maximum_qqq_proxy_constituent_weight_ratio"])
            + Decimal(predecessor["minimum_resolved_constituent_weight_ratio"])
            == 1
        )
    assert low_precision["run_valid"] is True


def test_skipped_unpriced_evidence_is_complete_redacted_bounded_and_noncurative(
    monkeypatch,
):
    def predecessor_positive_price(_self, _security_id, _session):
        return None

    def predecessor_build_plan(self, session, target_weights):
        for security_id in sorted(target_weights):
            self._positive_price(security_id, session)
        self._skipped_unpriced_decision_count += 1
        return None

    monkeypatch.setattr(
        v13.AcceptedRiskQqqOrderLevelV13QcRuntime,
        "_positive_price",
        predecessor_positive_price,
    )
    monkeypatch.setattr(
        v13.AcceptedRiskQqqOrderLevelV13QcRuntime,
        "_build_plan",
        predecessor_build_plan,
    )
    value = _runtime()
    raw_security_ids = []
    for day in range(5):
        security_ids = [
            f"raw-security-{day}-{index}" for index in range(6)
        ]
        raw_security_ids.extend(security_ids)
        assert value._build_plan(
            f"2026-01-{5 + day:02d}",
            {security_id: Decimal("0.1") for security_id in security_ids},
        ) is None

    predecessor = _summary(skipped=5, run_valid=False)
    monkeypatch.setattr(
        v13.AcceptedRiskQqqOrderLevelV13QcRuntime,
        "_aggregate_record",
        lambda _self: dict(predecessor),
    )
    value._pit_coverage_records = _coverage_records()
    summary = value._aggregate_record()
    evidence = summary["skipped_unpriced_decision_evidence"]

    assert summary["run_valid"] is False
    assert evidence["schema"] == runtime.SKIPPED_UNPRICED_EVIDENCE_SCHEMA
    assert evidence["skipped_decision_count"] == 5
    assert evidence["retained_decision_count"] == 4
    assert evidence["omitted_decision_count"] == 1
    assert len(evidence["records"]) == 4
    assert all(
        record["missing_security_count"] == 6
        and len(record["retained_missing_security_sha256s"]) == 4
        and record["omitted_missing_security_count"] == 2
        and len(record["missing_security_path_sha256"]) == 64
        for record in evidence["records"]
    )
    assert len(evidence["path_sha256"]) == 64
    encoded = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    assert len(encoded.encode("ascii")) < 3_000
    assert not any(security_id in encoded for security_id in raw_security_ids)

    expected_full_records = []
    for day in range(5):
        expected_security_sha256s = sorted(
            runtime._redacted_security_id_sha256(
                f"raw-security-{day}-{index}"
            )
            for index in range(6)
        )
        expected_full_records.append({
            "decision_session": f"2026-01-{5 + day:02d}",
            "missing_security_sha256s": expected_security_sha256s,
        })
        if day < runtime.MAXIMUM_RETAINED_SKIPPED_DECISIONS:
            record = evidence["records"][day]
            assert record["retained_missing_security_sha256s"] == (
                expected_security_sha256s[
                    :runtime.MAXIMUM_RETAINED_MISSING_SECURITY_HASHES
                ]
            )
            assert record["missing_security_path_sha256"] == legacy._sha({
                "schema": runtime.MISSING_SECURITY_PATH_SCHEMA,
                "security_sha256s": expected_security_sha256s,
            })
    assert evidence["path_sha256"] == legacy._sha({
        "schema": runtime.SKIPPED_UNPRICED_PATH_SCHEMA,
        "records": expected_full_records,
    })


def test_skipped_unpriced_evidence_count_mismatch_refuses(monkeypatch):
    value = _runtime()
    value._pit_coverage_records = _coverage_records()
    value._skipped_unpriced_evidence_records = [{
        "decision_session": "2026-01-05",
        "missing_security_sha256s": ["a" * 64],
    }]
    monkeypatch.setattr(
        v13.AcceptedRiskQqqOrderLevelV13QcRuntime,
        "_aggregate_record",
        lambda _self: _summary(skipped=0, run_valid=True),
    )

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^order-level skipped decision evidence count changed$",
    ):
        value._aggregate_record()


def test_v14_end_callback_binds_fresh_profile_summary_and_meta(monkeypatch):
    value, algorithm, aggregate = _end_ready(
        datetime.fromisoformat("2026-09-18T00:00:00")
    )
    monkeypatch.setattr(legacy, "MAXIMUM_STATISTIC_BYTES", 8_192)

    value.on_end_of_algorithm()

    assert json.loads(
        algorithm.summary_statistics[legacy.AGGREGATES_STATISTIC_NAME]
    ) == aggregate
    meta = json.loads(
        algorithm.summary_statistics[legacy.META_STATISTIC_NAME]
    )
    assert meta["schema"] == "arv2-qqq-order-level-tilt-runtime-meta-v3"
    assert meta["profile_id"] == runtime.DIAGNOSTIC_PROFILE_2026_ID
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
def test_v14_end_callback_refuses_every_other_clock_atomically(callback_time):
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
def test_v14_end_callback_refuses_invalid_runtime_state_before_output(
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


def test_v14_end_callback_refuses_pending_preopen_plan_before_output():
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
    assert value._completed is False


def test_v14_end_callback_refuses_incomplete_decision_schedule_before_output():
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
    assert value._completed is False


def test_v14_end_callback_refuses_oversized_aggregate_before_output(
    monkeypatch,
):
    value, algorithm, _aggregate = _end_ready(
        datetime.fromisoformat("2026-09-18T00:00:00")
    )
    value._aggregate_record = lambda: {"oversized": "x" * 8_192}
    monkeypatch.setattr(legacy, "MAXIMUM_STATISTIC_BYTES", 8_192)

    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^order-level aggregate transport exceeded its exact bound$",
    ):
        value.on_end_of_algorithm()

    assert algorithm.summary_statistics == {}
    assert value._completed is False


def test_v14_unknown_profile_refuses_before_v13_initialization():
    with pytest.raises(
        runtime.AcceptedRiskQqqOrderLevelQcRuntimeError,
        match="^QQQ order-level V14 profile is not an exact fixed profile$",
    ):
        _runtime(profile_id=v13.ROLLOVER_PROFILE_2026_ID)
