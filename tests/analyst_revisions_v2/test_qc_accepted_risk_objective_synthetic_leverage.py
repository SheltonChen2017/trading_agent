import ast
import hashlib
import json
from datetime import date
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2_qc import (
    accepted_risk_market_cap_stock_portfolio_evaluator as market,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_objective_synthetic_leverage_evaluator as subject,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_preliminary_rating_evaluator as base,
)


def _sessions():
    return tuple(
        session.isoformat()
        for session in trading_sessions(
            date(2013, 1, 2), date(2026, 4, 30)
        )
    )


def _input():
    sessions = _sessions()
    session_rows = tuple(
        {
            "schema": base.SESSION_SCHEMA,
            "session_index": index,
            "session": session,
        }
        for index, session in enumerate(sessions)
    )
    memberships = tuple(
        base.build_membership_record(
            security_id=f"perm-security-{index:02d}",
            first_session_index=0,
            last_session_index_exclusive=len(sessions),
            sector_id="sector-technology",
        )
        for index in range(20)
    )
    contributions = []
    contribution_sessions = tuple(
        sessions.index(
            next(
                session
                for session in sessions
                if session.startswith(f"{year}-")
            )
        )
        for year in range(2018, 2026)
    )
    for view in base.SOURCE_VIEW_IDS:
        for contribution_session in contribution_sessions:
            for index in range(20):
                delta = Fraction(index - 10 if index < 10 else index - 9, 10)
                contributions.append(
                    base.build_contribution_record(
                        source_view_id=view,
                        security_id=f"perm-security-{index:02d}",
                        eligible_session_index=contribution_session,
                        institution_id=f"firm-{index:02d}",
                        common_event_id=(
                            f"event-{contribution_session}-{index:02d}"
                        ),
                        rating_action=(
                            "downgrades" if index < 10 else "upgrades"
                        ),
                        firm_delta=delta,
                        global_delta=delta / 2,
                        source_row_sha256=hashlib.sha256(
                            f"source-{view}-{contribution_session}-{index}".encode(
                                "ascii"
                            )
                        ).hexdigest(),
                    )
                )
    lineage = {
        name: hashlib.sha256(name.encode("ascii")).hexdigest()
        for name in base._SOURCE_LINEAGE_FIELDS
    }
    manifest = base.build_preliminary_rating_manifest(
        benchmark_security_id="benchmark-SPY-permanent-id",
        session_axis_records=session_rows,
        membership_records=memberships,
        contribution_records=tuple(contributions),
        source_lineage_sha256s=lineage,
        history_batch_security_count=64,
        scoring_sessions_per_callback=5,
        signal_seed_contributions_per_callback=20_000,
    )
    return base.load_preliminary_rating_input(
        manifest,
        session_rows,
        memberships,
        tuple(contributions),
    )


def _caps(value, profile_id):
    base_profile_id = subject.require_profile(profile_id)["base_profile_id"]
    cap_by_security = {
        security_id: Decimal(index + 1)
        for index, security_id in enumerate(
            sorted(item.security_id for item in value.memberships)
        )
    }
    return {
        session: dict(cap_by_security)
        for session in market.decision_sessions_for_input(
            value, base_profile_id
        )
    }


def _history_loader(value, *, daily_growth=Decimal("1.0001")):
    positions = {
        session: index for index, session in enumerate(value.session_axis)
    }

    def load(request):
        rows = []
        begin = positions[request.start_session]
        end = positions[request.end_session]
        for security_index, security_id in enumerate(request.security_ids):
            price = Decimal(100 + security_index)
            for session in value.session_axis[begin : end + 1]:
                rows.append(
                    base.TotalReturnOpenObservation(
                        base.HISTORY_OBSERVATION_SCHEMA,
                        security_id,
                        session,
                        price,
                    )
                )
                if security_id == value.benchmark_security_id:
                    price *= daily_growth
                elif security_index % 2:
                    price *= Decimal("1.0002")
                else:
                    price *= Decimal("0.9999")
        return tuple(rows)

    return load


def _complete(profile_id=subject.QQQ_2021_2025_V2_PROFILE_ID):
    value = _input()
    runtime = subject.ObjectiveSyntheticLeverageEvaluationRuntime(
        value,
        profile_id=profile_id,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        named_figi_resolution_refusals=(),
        eligibility_market_caps_by_decision_session=_caps(value, profile_id),
    )
    loader = _history_loader(value)
    while runtime.phase is not base.RuntimePhase.COMPLETED:
        runtime.run_callback(loader)
    return runtime


def test_two_successor_profiles_pin_exact_base_lineage_and_objective_rule():
    assert subject.PROFILE_IDS == (
        subject.QQQ_2021_2025_V2_PROFILE_ID,
        subject.SPY_2021_2025_V2_PROFILE_ID,
    )
    assert subject.ALL_PROFILE_IDS == subject.V1_PROFILE_IDS + subject.PROFILE_IDS
    expected = {
        subject.QQQ_2021_2025_V2_PROFILE_ID: (
            market.QQQ_2021_2025_V2_PROFILE_ID,
            "71fe35e9a200e61c9c908fe839e244d97bcef89664a921ddaa3dfd09b8a09178",
        ),
        subject.SPY_2021_2025_V2_PROFILE_ID: (
            market.SPY_2021_2025_V2_PROFILE_ID,
            "0b6587206c68452b7468aff42432cb3b587a0f96cc078fbf57a6473f86feb59d",
        ),
    }
    for profile_id, (base_id, base_sha) in expected.items():
        profile = subject.require_profile(profile_id)
        digest = profile.pop("profile_sha256")
        assert subject._sha(profile) == digest
        assert profile["base_profile_id"] == base_id
        assert profile["base_profile_sha256"] == base_sha
        assert profile["base_evaluator_source_sha256"] == (
            subject.BASE_EVALUATOR_SOURCE_SHA256
        )
        assert profile["leverage_factors"] == [2, 3]
        assert profile["synthetic_only"] is True
        assert profile["financing_notional_rule"] == (
            "one_full_base_portfolio_unit_when_the_session_began_invested_"
            "without_netting_cash_or_underfill"
        )
        assert profile["orders"] is False
        assert profile["deployment"] is False
        assert profile["trading"] is False
        assert "without_hindsight_or_security_override" in profile[
            "signal_and_selection"
        ]
    assert all(
        subject.require_profile(profile_id)["base_evaluator_source_sha256"]
        == subject.V1_BASE_EVALUATOR_SOURCE_SHA256
        for profile_id in subject.V1_PROFILE_IDS
    )


def test_base_evaluator_source_bytes_and_profile_hashes_are_still_exact():
    assert hashlib.sha256(Path(market.__file__).read_bytes()).hexdigest() == (
        subject.BASE_EVALUATOR_SOURCE_SHA256
    )
    for leverage_id in subject.PROFILE_IDS:
        profile = subject.require_profile(leverage_id)
        base_profile = market.require_profile(profile["base_profile_id"])
        assert base_profile["profile_sha256"] == profile[
            "base_profile_sha256"
        ]


def test_preserved_v1_profile_emits_its_historical_source_identity():
    runtime = _complete(subject.QQQ_2021_2025_PROFILE_ID)
    meta = json.loads(runtime.custom_summary_statistics()["ARV2_LEVERAGE_META"])

    assert meta["base_evaluator_source_sha256"] == (
        subject.V1_BASE_EVALUATOR_SOURCE_SHA256
    )


def test_scenarios_and_custom_stat_inventory_are_fixed():
    assert subject.LEVERAGE_FACTORS == (2, 3)
    assert subject.SCENARIOS == (
        (
            subject.PRIMARY_SCENARIO_ID,
            Decimal("0.06"),
            10,
            True,
        ),
        (
            subject.ADVERSE_SCENARIO_ID,
            Decimal("0.10"),
            20,
            False,
        ),
    )
    assert subject.expected_custom_summary_statistic_names(
        subject.QQQ_2021_2025_V2_PROFILE_ID
    ) == (
        "ARV2_LEVERAGE_L2_ADVERSE",
        "ARV2_LEVERAGE_L2_PRIMARY",
        "ARV2_LEVERAGE_L3_ADVERSE",
        "ARV2_LEVERAGE_L3_PRIMARY",
        "ARV2_LEVERAGE_META",
    )
    with pytest.raises(
        subject.ObjectiveSyntheticLeverageEvaluationError,
        match="exact fixed profile",
    ):
        subject.require_profile("unknown")


def test_daily_reset_formula_charges_only_sessions_that_began_invested():
    returns = (Decimal("-0.001"), Decimal("0.01"), Decimal("-0.02"))
    flags = (False, True, False)
    path = subject._apply_daily_reset_leverage(
        returns,
        flags,
        leverage_factor=2,
        annual_financing_rate=Decimal("0.06"),
    )
    with localcontext(base._context()):
        charge = +(Decimal("0.06") / Decimal(252))
        expected = (
            Decimal("-0.002"),
            +(Decimal("0.02") - charge),
            Decimal("-0.04"),
        )
        wealth = Decimal(1)
        unfinanced = Decimal(1)
        for value, underlying in zip(expected, returns, strict=True):
            wealth = +(wealth * (Decimal(1) + value))
            unfinanced = +(
                unfinanced * (Decimal(1) + Decimal(2) * underlying)
            )
        expected_cumulative = +(wealth - Decimal(1))
        expected_unfinanced = +(unfinanced - Decimal(1))
        expected_drag = +(unfinanced - wealth)
    assert path.returns == expected
    assert path.financing_session_count == 1
    assert path.arithmetic_financing_debit == charge
    assert path.cumulative_return == expected_cumulative
    assert path.cumulative_return_before_financing == expected_unfinanced
    assert path.cumulative_financing_drag == expected_drag


@pytest.mark.parametrize(
    ("returns", "flags", "factor", "rate", "message"),
    (
        ([], (), 2, Decimal("0.06"), "nonempty exact Decimal tuple"),
        ((Decimal(0),), (), 2, Decimal("0.06"), "flags changed"),
        ((Decimal(0),), (False,), 4, Decimal("0.06"), "factor is not exact"),
        ((Decimal(0),), (False,), 2, Decimal("-0.01"), "rate is invalid"),
        ((Decimal("-0.5"),), (False,), 2, Decimal(0), "not survivable"),
        (
            (Decimal("-0.4999"),),
            (True,),
            2,
            Decimal("0.06"),
            "not survivable",
        ),
    ),
)
def test_daily_reset_formula_refuses_malformed_or_wiped_out_paths(
    returns, flags, factor, rate, message
):
    with pytest.raises(
        subject.ObjectiveSyntheticLeverageEvaluationError,
        match=message,
    ):
        subject._apply_daily_reset_leverage(
            returns,
            flags,
            leverage_factor=factor,
            annual_financing_rate=rate,
        )


@pytest.mark.parametrize("profile_id", subject.PROFILE_IDS)
def test_runtime_emits_four_exact_cells_with_identical_comparator_treatment(
    profile_id, monkeypatch
):
    routed = []
    apply_leverage = subject._apply_daily_reset_leverage

    def capture(returns, flags, *, leverage_factor, annual_financing_rate):
        routed.append(
            (leverage_factor, annual_financing_rate, returns, flags)
        )
        return apply_leverage(
            returns,
            flags,
            leverage_factor=leverage_factor,
            annual_financing_rate=annual_financing_rate,
        )

    monkeypatch.setattr(subject, "_apply_daily_reset_leverage", capture)
    runtime = _complete(profile_id)
    summary = runtime.aggregate_summary()
    assert summary["profile"]["profile_id"] == profile_id
    assert summary["base_profile_id"] == summary["profile"][
        "base_profile_id"
    ]
    assert summary["base_profile_sha256"] == summary["profile"][
        "base_profile_sha256"
    ]
    assert summary["r055_signal_rule_changed"] is False
    assert summary["base_security_selection_changed"] is False
    assert summary["matched_comparator_levered_identically"] is True
    assert summary["return_session_count"] == 1_254
    assert len(summary["cells"]) == 4
    assert {
        (
            cell["leverage_factor"],
            cell["scenario_id"],
            cell["annual_financing_rate"],
            cell["underlying_cost_bps_per_side"],
        )
        for cell in summary["cells"]
    } == {
        (2, subject.PRIMARY_SCENARIO_ID, "0.06", 10),
        (2, subject.ADVERSE_SCENARIO_ID, "0.10", 20),
        (3, subject.PRIMARY_SCENARIO_ID, "0.06", 10),
        (3, subject.ADVERSE_SCENARIO_ID, "0.10", 20),
    }
    for cell in summary["cells"]:
        assert cell["selected_financing_session_count"] == 1_253
        assert cell["matched_financing_session_count"] == 1_253
        assert cell["synthetic_spy_financing_session_count"] == 1_253
        assert cell["underlying_cost_is_already_in_base_return"] is True
        assert cell["second_transaction_cost_deduction"] is False
        assert cell["synthetic_only"] is True
        assert cell["margin_calls_modeled"] is False
        assert cell["borrow_availability_modeled"] is False
        assert cell["security_level_financing_modeled"] is False
        assert cell["broker_liquidation_modeled"] is False
        assert cell["orders_submitted"] == 0
        selected_debit = Decimal(cell["selected_arithmetic_financing_debit"])
        matched_debit = Decimal(cell["matched_arithmetic_financing_debit"])
        assert selected_debit == matched_debit
        with localcontext(base._context()):
            expected_debit = +(
                Decimal(cell["leverage_factor"] - 1)
                * Decimal(cell["annual_financing_rate"])
                / Decimal(252)
                * Decimal(1_253)
            )
        assert selected_debit == expected_debit
    assert len(routed) == 12
    assert routed[0][0:2] == (2, Decimal("0.06"))
    assert routed[0][2][0] == Decimal("-0.00098")
    assert routed[1][0:2] == routed[0][0:2]
    assert routed[1][2] != routed[0][2]
    assert routed[3][0:2] == (2, Decimal("0.10"))
    assert routed[3][2][0] == Decimal("-0.00196")
    assert routed[4][0:2] == routed[3][0:2]
    assert routed[4][2] != routed[3][2]
    assert routed[2][2] == routed[5][2]
    assert routed[2][2][0] == 0
    assert routed[0][3][0] is False
    assert all(routed[0][3][1:])
    assert routed[6][0:2] == (3, Decimal("0.06"))
    assert routed[9][0:2] == (3, Decimal("0.10"))


def test_custom_summary_is_compact_aggregate_only_and_has_no_capabilities():
    runtime = _complete()
    output = runtime.custom_summary_statistics()
    assert tuple(output) == subject.expected_custom_summary_statistic_names(
        subject.QQQ_2021_2025_V2_PROFILE_ID
    )
    assert all(len(key) <= 64 and len(value) <= 4096 for key, value in output.items())
    joined = json.dumps(output, sort_keys=True)
    assert "perm-security" not in joined
    assert "benchmark-SPY-permanent-id" not in joined
    assert "firm-" not in joined
    assert "event-" not in joined
    meta = json.loads(output["ARV2_LEVERAGE_META"])
    assert meta["raw_security_ids_in_summary"] is False
    assert meta["raw_price_rows_in_summary"] is False
    assert meta["raw_provider_rows_in_summary"] is False
    assert meta["evaluator_io"] == {
        "provider": False,
        "network": False,
        "object_store": False,
    }
    assert meta["orders"] is False
    assert meta["deployment"] is False
    assert meta["trading"] is False


def test_module_has_no_io_network_order_or_deployment_import_surface():
    source = Path(subject.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        node.names[0].name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
    }
    imports.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not imports.intersection(
        {
            "http",
            "requests",
            "socket",
            "subprocess",
            "urllib",
            "quantconnect",
            "lean",
            "broker",
        }
    )
    assert "AlgorithmImports" not in source
    assert "ObjectStore" not in source
    assert "MarketOrder" not in source
    assert "SetHoldings" not in source


def test_daily_reset_compounds_each_levered_session_not_the_cumulative_underlying():
    """ARV2R93: isolate the daily-reset semantics from the financing tests."""

    returns = (Decimal("0.10"), Decimal("-0.10"))
    flags = (True, True)
    path = subject._apply_daily_reset_leverage(
        returns,
        flags,
        leverage_factor=2,
        annual_financing_rate=Decimal(0),
    )

    # A daily reset compounds each levered session: (1.20)(0.80) - 1 = -4%.
    # Levering the cumulative underlying instead would give 2 x ((1.10)(0.90) - 1) = -2%.
    assert path.returns == (Decimal("0.20"), Decimal("-0.20"))
    assert path.cumulative_return == Decimal("-0.04")
    assert path.cumulative_return_before_financing == Decimal("-0.04")
    assert path.cumulative_financing_drag == 0
    assert path.financing_session_count == 2
