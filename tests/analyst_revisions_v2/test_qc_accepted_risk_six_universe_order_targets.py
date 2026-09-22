import dataclasses
import json
from decimal import Decimal

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_gate as gate,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_gate_evaluator as evaluator,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_targets as subject,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_market_cap_stock_portfolio as input_fixtures,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_six_universe_gate_evaluator as gate_fixtures,
)


def _runtime(value, snapshots):
    return evaluator.SixUniverseGateEvaluationRuntime(
        value,
        profile_id=evaluator.TOP10_PRIMARY_PROFILE.profile_id,
        package_id="arv2-test-package",
        package_sha256="a" * 64,
        symbol_resolution_id="arv2-test-resolution",
        symbol_resolution_sha256="b" * 64,
        decision_snapshots=snapshots,
    )


def _weight_rows(weights):
    return tuple(
        (item.security_id, item.asset_kind, item.weight) for item in weights
    )


@pytest.mark.parametrize(
    ("role", "attribute"),
    (
        (subject.ROLE_SIGNAL, "signal_weights"),
        (subject.ROLE_MATCHED, "matched_weights"),
        (subject.ROLE_SIX_ETF_BASKET, "etf_basket_weights"),
    ),
)
def test_all_roles_are_exactly_parity_bound_to_the_frozen_evaluator(
    role,
    attribute,
):
    value = input_fixtures._input(20)
    snapshots = gate_fixtures._snapshots(value)
    expected = _runtime(value, snapshots)

    path = subject.build_six_universe_order_target_path(
        value,
        snapshots,
        role=role,
    )

    assert path.construction_path_sha256 == expected._construction_path_sha256
    assert len(path.decisions) == len(expected._decisions) == 261
    for decision in path.decisions:
        construction = expected._decisions[decision.session].construction
        record = construction.to_record()
        assert decision.construction_id == record["construction_id"]
        assert decision.construction_sha256 == record["construction_sha256"]
        assert _weight_rows(decision.target_weights) == _weight_rows(
            getattr(construction, attribute)
        )
    record = path.to_record()
    assert record["role"] == role
    assert record["decision_count"] == 261
    assert record["target_path_sha256"] == path.target_path_sha256
    json.dumps(record, allow_nan=False).encode("ascii")


def test_streaming_builder_needs_only_the_next_snapshot_and_advances_monotonically():
    value = input_fixtures._input(20)
    snapshots = gate_fixtures._snapshots(value)
    builder = subject.SixUniverseOrderTargetBuilder(
        value,
        role=subject.ROLE_SIGNAL,
    )

    assert builder.next_required_session == snapshots[0].session
    first = builder.build(snapshots[0].session, snapshots[0])
    assert first.session == snapshots[0].session
    assert builder.decisions == (first,)
    assert builder.next_required_session == snapshots[1].session
    with pytest.raises(
        subject.SixUniverseOrderTargetsError,
        match="exact next session",
    ):
        builder.build(snapshots[2].session, snapshots[2])
    second = builder.build(snapshots[1].session, snapshots[1])
    assert builder.decisions == (first, second)
    with pytest.raises(
        subject.SixUniverseOrderTargetsError,
        match="before completion",
    ):
        builder.complete_path()


def test_overlapping_members_aggregate_once_and_respect_the_direct_stock_cap():
    value = input_fixtures._input(20)
    snapshots = gate_fixtures._snapshots(value)
    decision = subject.SixUniverseOrderTargetBuilder(
        value,
        role=subject.ROLE_SIGNAL,
    ).build(snapshots[0].session, snapshots[0])

    stocks = tuple(
        item for item in decision.target_weights if item.asset_kind == "stock"
    )
    assert len(stocks) == 10
    assert len({item.security_id for item in stocks}) == len(stocks)
    assert all(item.weight == gate.DIRECT_STOCK_WEIGHT_CAP for item in stocks)
    assert sum((item.weight for item in stocks), Decimal(0)) == Decimal("0.98")
    assert all(
        sleeve.selection_status == "FULL_STOCK_SLOTS"
        and sleeve.etf_target_weight == 0
        for sleeve in decision.sleeves
    )


def test_fewer_than_five_positive_scores_produces_exact_own_etf_fallbacks():
    value = input_fixtures._input(8)
    snapshots = gate_fixtures._snapshots(value)
    decision = subject.SixUniverseOrderTargetBuilder(
        value,
        role=subject.ROLE_SIGNAL,
    ).build(snapshots[0].session, snapshots[0])

    assert len(decision.target_weights) == 6
    assert all(item.asset_kind == "etf" for item in decision.target_weights)
    assert sum(
        (item.weight for item in decision.target_weights), Decimal(0)
    ) == gate.TARGET_GROSS_EXPOSURE
    for index, sleeve in enumerate(decision.sleeves):
        assert sleeve.positive_score_count < gate.MINIMUM_POSITIVE_SCORE_COUNT
        assert sleeve.selected_security_ids == ()
        assert sleeve.post_cap_stock_target_count == 0
        assert sleeve.etf_target_weight == gate.SLEEVE_BUDGETS[index]
        assert sleeve.selection_status == "POSITIVE_SCORE_FLOOR_FALLBACK"


@pytest.mark.parametrize("role", (None, "", "selected", 1))
def test_unfrozen_target_role_refuses_before_scoring(role):
    value = input_fixtures._input(20)
    with pytest.raises(
        subject.SixUniverseOrderTargetsError,
        match="role is not frozen",
    ):
        subject.SixUniverseOrderTargetBuilder(value, role=role)


def test_top_five_profile_cannot_enter_the_top_ten_order_builder():
    value = input_fixtures._input(20)
    with pytest.raises(
        subject.SixUniverseOrderTargetsError,
        match="not frozen top-ten",
    ):
        subject.SixUniverseOrderTargetBuilder(
            value,
            profile=evaluator.TOP5_SENSITIVITY_PROFILE,
            role=subject.ROLE_SIGNAL,
        )


def test_injected_score_closes_streaming_builder_after_the_failed_advance():
    value = input_fixtures._input(20)
    snapshots = gate_fixtures._snapshots(value)
    first = snapshots[0]
    universe = first.universes[0]
    row = dataclasses.replace(
        universe.constituents[0],
        firm_specific_score=Decimal(1),
    )
    injected = dataclasses.replace(
        first,
        universes=(
            dataclasses.replace(
                universe,
                constituents=(row, *universe.constituents[1:]),
            ),
            *first.universes[1:],
        ),
    )
    builder = subject.SixUniverseOrderTargetBuilder(
        value,
        role=subject.ROLE_SIGNAL,
    )

    with pytest.raises(
        subject.SixUniverseOrderTargetsError,
        match="inject an R055 score",
    ):
        builder.build(first.session, injected)
    with pytest.raises(
        subject.SixUniverseOrderTargetsError,
        match="closed after failure",
    ):
        builder.build(first.session, first)


def test_records_are_frozen_and_hash_authenticated():
    value = input_fixtures._input(20)
    snapshots = gate_fixtures._snapshots(value)
    path = subject.build_six_universe_order_target_path(
        value,
        snapshots,
        role=subject.ROLE_SIX_ETF_BASKET,
    )
    decision = path.decisions[0]
    assert tuple(sleeve.etf_target_weight for sleeve in decision.sleeves) == (
        gate.SLEEVE_BUDGETS
    )
    assert all(
        sleeve.selection_status == "SIX_ETF_BASKET"
        for sleeve in decision.sleeves
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.role = subject.ROLE_SIGNAL
    corrupted = dataclasses.replace(decision, target_sha256="0" * 64)
    with pytest.raises(
        subject.SixUniverseOrderTargetsError,
        match="authority changed",
    ):
        corrupted.to_record()
    corrupted_path = dataclasses.replace(path, target_path_sha256="0" * 64)
    with pytest.raises(
        subject.SixUniverseOrderTargetsError,
        match="authority changed",
    ):
        corrupted_path.to_record()
