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


def _cap90_spy_snapshots(value):
    snapshots = gate_fixtures._snapshots(value)
    result = []
    for snapshot in snapshots:
        spy = snapshot.universes[0]
        rows = tuple(
            dataclasses.replace(row, pit_market_cap=None)
            if index < 2 else row
            for index, row in enumerate(spy.constituents)
        )
        result.append(
            dataclasses.replace(
                snapshot,
                universes=(
                    dataclasses.replace(spy, constituents=rows),
                    *snapshot.universes[1:],
                ),
            )
        )
    return tuple(result)


@pytest.mark.parametrize(
    "role",
    (subject.ROLE_SIGNAL, subject.ROLE_MATCHED, subject.ROLE_SIX_ETF_BASKET),
)
def test_cap90_explicit_unavailable_collection_preserves_own_etf_target(role):
    value = input_fixtures._input(20)
    first = gate_fixtures._snapshots(value)[0]
    unavailable = dataclasses.replace(
        first,
        universes=tuple(
            dataclasses.replace(universe, constituents=())
            if universe.universe_id == "REMX"
            else universe
            for universe in first.universes
        ),
    )
    builder = subject.SixUniverseOrderTargetBuilder(
        value,
        role=role,
        profile=subject.ORDER_CAP90_EVALUATION_PROFILE,
    )
    decision = builder.build(
        first.session, unavailable, unavailable_universe_ids=("REMX",)
    )
    remx = decision.sleeves[4]
    assert remx.coverage_refusal_reasons == ("CONSTITUENT_COLLECTION_UNAVAILABLE",)
    assert remx.coverage_valid is False
    assert remx.selected_security_ids == ()
    assert remx.post_cap_stock_target_count == 0
    assert remx.etf_target_weight == gate.SLEEVE_BUDGETS[4]
    assert remx.selection_status == (
        "SIX_ETF_BASKET" if role == subject.ROLE_SIX_ETF_BASKET
        else "COVERAGE_FALLBACK"
    )
    assert sum((item.weight for item in decision.target_weights), Decimal(0)) == (
        gate.TARGET_GROSS_EXPOSURE
    )
    assert decision.to_record()["target_sha256"] == decision.target_sha256


def test_order_target_default_still_refuses_unflagged_empty_collection():
    value = input_fixtures._input(20)
    first = gate_fixtures._snapshots(value)[0]
    empty = dataclasses.replace(
        first,
        universes=tuple(
            dataclasses.replace(universe, constituents=())
            if universe.universe_id == "REMX"
            else universe
            for universe in first.universes
        ),
    )
    for profile, flags in (
        (subject.ORDER_EVALUATION_PROFILE, ()),
        (subject.ORDER_EVALUATION_PROFILE, ("REMX",)),
        (subject.ORDER_CAP90_EVALUATION_PROFILE, ()),
    ):
        builder = subject.SixUniverseOrderTargetBuilder(
            value, role=subject.ROLE_SIGNAL, profile=profile
        )
        with pytest.raises(gate.SixUniverseGateError):
            builder.build(
                first.session, empty, unavailable_universe_ids=flags
            )
        assert builder.next_required_session is None


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


def test_default_order_path_retains_the_preexisting_r177_identity():
    value = input_fixtures._input(20)
    path = subject.build_six_universe_order_target_path(
        value,
        gate_fixtures._snapshots(value),
        role=subject.ROLE_SIGNAL,
    )
    assert path.evaluation_profile_id == evaluator.TOP10_PRIMARY_PROFILE.profile_id
    assert path.gate_profile_id == gate.TOP10_PRIMARY_PROFILE.profile_id
    assert path.target_path_sha256 == (
        "dbdc3144536b766e339fe0d62db6444ebd8c66ff47c36ab49622640784c66e33"
    )


@pytest.mark.parametrize(
    "role",
    (subject.ROLE_SIGNAL, subject.ROLE_MATCHED, subject.ROLE_SIX_ETF_BASKET),
)
def test_cap90_order_variant_is_explicit_and_preserves_matched_role_economics(role):
    value = input_fixtures._input(20)
    first = _cap90_spy_snapshots(value)[0]
    default = subject.SixUniverseOrderTargetBuilder(
        value, role=role
    ).build(first.session, first)
    cap90 = subject.SixUniverseOrderTargetBuilder(
        value,
        role=role,
        profile=subject.ORDER_CAP90_EVALUATION_PROFILE,
    ).build(first.session, first)

    assert default.sleeves[0].coverage_valid is False
    if role == subject.ROLE_SIX_ETF_BASKET:
        assert default.sleeves[0].selection_status == "SIX_ETF_BASKET"
    else:
        assert default.sleeves[0].selection_status == "COVERAGE_FALLBACK"
    assert cap90.sleeves[0].coverage_valid is True
    assert cap90.construction_sha256 != default.construction_sha256
    assert cap90.sleeves[0].slot_count == 10
    assert sum((item.weight for item in cap90.target_weights), Decimal(0)) == (
        gate.TARGET_GROSS_EXPOSURE
    )
    if role == subject.ROLE_SIX_ETF_BASKET:
        assert cap90.target_weights == default.target_weights
    else:
        assert cap90.sleeves[0].selected_security_ids
        assert cap90.sleeves[0].selection_status != "COVERAGE_FALLBACK"


def test_cap90_order_signal_and_matched_select_equal_spy_stock_counts():
    value = input_fixtures._input(20)
    first = _cap90_spy_snapshots(value)[0]
    decisions = {
        role: subject.SixUniverseOrderTargetBuilder(
            value,
            role=role,
            profile=subject.ORDER_CAP90_EVALUATION_PROFILE,
        ).build(first.session, first)
        for role in (subject.ROLE_SIGNAL, subject.ROLE_MATCHED)
    }
    signal, matched = (decisions[role].sleeves[0] for role in decisions)
    assert len(signal.selected_security_ids) == len(matched.selected_security_ids)
    assert signal.post_cap_stock_target_count == matched.post_cap_stock_target_count
    assert signal.etf_target_weight == matched.etf_target_weight


def test_cap90_order_path_binds_distinct_profile_and_refuses_unapproved_variants():
    value = input_fixtures._input(20)
    snapshots = _cap90_spy_snapshots(value)
    path = subject.build_six_universe_order_target_path(
        value,
        snapshots,
        role=subject.ROLE_SIGNAL,
        profile=subject.ORDER_CAP90_EVALUATION_PROFILE,
    )
    assert path.evaluation_profile_id == (
        evaluator.TOP10_CAP90_EXPLORATORY_PROFILE.profile_id
    )
    assert path.gate_profile_id == gate.TOP10_CAP90_EXPLORATORY_PROFILE.profile_id
    assert path.decisions[0].sleeves[0].coverage_valid is True
    assert path.to_record()["target_path_sha256"] == path.target_path_sha256

    for unapproved in (
        evaluator.TOP10_CAP95_EXPLORATORY_PROFILE,
        dataclasses.replace(evaluator.TOP10_CAP90_EXPLORATORY_PROFILE),
    ):
        with pytest.raises(
            subject.SixUniverseOrderTargetsError,
            match="not an approved top-ten order profile",
        ):
            subject.SixUniverseOrderTargetBuilder(
                value, role=subject.ROLE_SIGNAL, profile=unapproved
            )


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
