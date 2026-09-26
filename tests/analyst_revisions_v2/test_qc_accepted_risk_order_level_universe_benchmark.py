from decimal import Decimal
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_order_level_benchmark as legacy,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_order_level_universe_benchmark as subject,
)


class _Refusal(ValueError):
    pass


def _spy_resolved(*, minimum_ratio=Decimal("0.50")):
    return subject.resolved_universe_holdings_weight_core(
        {
            "QC-A": Decimal("0.60"),
            "QC-B": Decimal("0.25"),
            "QC-C": Decimal("0.15"),
        },
        (
            {
                "qc_security_id": "QC-A",
                "security_id": "security-a",
            },
            {
                "qc_security_id": "QC-B",
                "security_id": "security-b",
            },
        ),
        ticker="SPY",
        proxy_record_prefix="spy",
        session="2025-01-02",
        constituent_age_sessions=1,
        minimum_total=Decimal("0.95"),
        maximum_total=Decimal("1.05"),
        minimum_resolved_ratio=minimum_ratio,
        weight_map_schema="arv2-order-level-spy-target-weight-map-v1",
        error_type=_Refusal,
        proxy_security_id="arv2-spy-etf-unjoined-weight-proxy",
        proxy_sid="QC-SPY",
    )


def test_module_has_no_fixed_legacy_universe_semantic_label():
    source = Path(subject.__file__).read_text(encoding="utf-8")
    assert "QQQ" not in source


def test_economic_constants_and_path_arithmetic_match_frozen_helper():
    assert subject.TARGET_GROSS_EXPOSURE == legacy.TARGET_GROSS_EXPOSURE
    assert subject.ENTRY_FEE_RATE_PER_SIDE == legacy.ENTRY_FEE_RATE_PER_SIDE
    assert subject.ENTRY_FEE_BPS_PER_SIDE == legacy.ENTRY_FEE_BPS_PER_SIDE

    sessions = ("2025-01-02", "2025-01-03", "2025-01-06")
    closes = tuple(
        zip(
            sessions,
            (Decimal("100"), Decimal("102"), Decimal("99")),
            strict=True,
        )
    )
    opens = {
        "2025-01-02": Decimal("99"),
        "2025-01-03": Decimal("101"),
        "2025-01-06": Decimal("100"),
    }
    expected_path, expected_binding = legacy.execution_matched_qqq_path(
        close_observations=closes,
        open_observations=opens,
        expected_sessions=sessions,
        first_execution_session="2025-01-03",
    )
    actual_path, actual_binding = subject.execution_matched_benchmark_path(
        close_observations=closes,
        open_observations=opens,
        expected_sessions=sessions,
        first_execution_session="2025-01-03",
        ticker="SPY",
        raw_input_schema="arv2-order-level-spy-execution-input-v1",
        path_schema="arv2-order-level-spy-execution-path-v1",
    )

    assert actual_path == expected_path
    assert subject.path_metrics(actual_path) == legacy.path_metrics(
        expected_path
    )
    assert {
        key: actual_binding[key]
        for key in (
            "normalization_mode",
            "observation",
            "first_execution_session",
            "target_gross_exposure",
            "entry_fee_bps_per_side",
            "observation_count",
            "return_interval_count",
        )
    } == {
        key: expected_binding[key]
        for key in (
            "normalization_mode",
            "observation",
            "first_execution_session",
            "target_gross_exposure",
            "entry_fee_bps_per_side",
            "observation_count",
            "return_interval_count",
        )
    }
    assert actual_binding["logical_benchmark_id"] == "SPY"
    assert actual_binding["raw_observation_sha256"] != (
        expected_binding["raw_observation_sha256"]
    )
    assert actual_binding["return_path_sha256"] != (
        expected_binding["return_path_sha256"]
    )


def test_spy_proxy_record_uses_only_caller_bound_record_keys():
    result, record = _spy_resolved()

    assert result == {
        "arv2-spy-etf-unjoined-weight-proxy": Decimal("0.15"),
        "security-a": Decimal("0.60"),
        "security-b": Decimal("0.25"),
    }
    assert record == {
        "session": "2025-01-02",
        "positive_weight_member_count": 3,
        "resolved_positive_weight_member_count": 2,
        "resolved_member_count_ratio": "0.6666666666666666666666666666666666666666666666666666666666666666666666666666666666666666666666666667",
        "resolved_constituent_weight_ratio": "0.85",
        "positive_constituent_weight_total": "1",
        "constituent_snapshot_age_sessions": 1,
        "pit_constituent_weight_map_sha256": (
            "eb7cf7b8eeb8103fc63720b69e6677311772260cd9a2eb770e6eec2420385554"
        ),
        "spy_proxy_constituent_weight_ratio": "0.15",
        "spy_proxy_reported_weight": "0.15",
    }
    assert all("qqq" not in key.lower() for key in record)


def test_generic_weight_core_reproduces_frozen_helper_when_bound_identically():
    weights = {
        "QC-A": Decimal("0.60"),
        "QC-B": Decimal("0.25"),
        "QC-C": Decimal("0.15"),
    }
    resolved = (
        {"qc_security_id": "QC-A", "security_id": "security-a"},
        {"qc_security_id": "QC-B", "security_id": "security-b"},
    )
    common = {
        "session": "2025-01-02",
        "constituent_age_sessions": 1,
        "minimum_total": Decimal("0.95"),
        "maximum_total": Decimal("1.05"),
        "minimum_resolved_ratio": Decimal("0.50"),
        "weight_map_schema": "arv2-order-level-pit-target-weight-map-v2",
        "error_type": _Refusal,
        "proxy_security_id": "arv2-qqq-etf-unjoined-weight-proxy",
    }
    frozen = legacy.resolved_qqq_holdings_weight_core(
        weights,
        resolved,
        qqq_sid="QC-QQQ",
        **common,
    )
    generic = subject.resolved_universe_holdings_weight_core(
        weights,
        resolved,
        ticker="QQQ",
        proxy_record_prefix="qqq",
        proxy_sid="QC-QQQ",
        **common,
    )

    assert generic == frozen


def test_spy_close_binding_binds_exact_ticker_and_schema_identity():
    sessions = ("2025-01-02", "2025-01-03", "2025-01-06")
    observations = (
        (sessions[0], Decimal("100")),
        (sessions[1], Decimal("105")),
        (sessions[2], Decimal("103")),
    )
    spy = subject.benchmark_close_binding(
        observations,
        sessions,
        ticker="SPY",
        raw_observations_schema=(
            "arv2-order-level-spy-total-return-close-observations-v1"
        ),
        return_path_schema=(
            "arv2-order-level-spy-total-return-close-path-v1"
        ),
    )
    alternate = subject.benchmark_close_binding(
        observations,
        sessions,
        ticker="DIA",
        raw_observations_schema=(
            "arv2-order-level-dia-total-return-close-observations-v1"
        ),
        return_path_schema=(
            "arv2-order-level-dia-total-return-close-path-v1"
        ),
    )

    assert spy["logical_benchmark_id"] == "SPY"
    assert spy["observation_count"] == 3
    assert spy["return_interval_count"] == 2
    assert spy["raw_observation_sha256"] != alternate["raw_observation_sha256"]
    assert spy["return_path_sha256"] != alternate["return_path_sha256"]
    assert subject.benchmark_total_return(
        observations, ticker="SPY"
    ) == Decimal("0.03")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"ticker": "spy"}, "ticker is invalid"),
        (
            {"raw_observations_schema": "contains spaces"},
            "raw-observations schema is invalid",
        ),
    ),
)
def test_close_binding_refuses_unbound_semantic_identity(kwargs, message):
    arguments = {
        "ticker": "SPY",
        "raw_observations_schema": "arv2-spy-raw-v1",
        "return_path_schema": "arv2-spy-path-v1",
    }
    arguments.update(kwargs)
    with pytest.raises(
        subject.AcceptedRiskOrderLevelUniverseBenchmarkError,
        match=message,
    ):
        subject.benchmark_close_binding(
            (("2025-01-02", Decimal("1")), ("2025-01-03", Decimal("1"))),
            ("2025-01-02", "2025-01-03"),
            **arguments,
        )


def test_proxy_floor_refusal_names_only_the_bound_universe():
    with pytest.raises(
        _Refusal,
        match=(
            "order-level PIT SPY resolved constituent-weight coverage is "
            "below its fixed floor: 0.85"
        ),
    ) as caught:
        _spy_resolved(minimum_ratio=Decimal("0.90"))
    assert "QQQ" not in str(caught.value)
