import dataclasses
import hashlib
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_gate as gate,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_qc_runtime as runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_targets as frozen_targets,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_tilt_targets as subject,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_six_universe_gate as fixtures,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_market_cap_stock_portfolio as input_fixtures,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_six_universe_gate_evaluator as gate_fixtures,
)


def _construction(snapshots):
    return gate.build_six_universe_construction(
        snapshots,
        gate.TOP10_CAP90_EXPLORATORY_PROFILE,
    )


def _by_id(weights):
    return {item.security_id: item.weight for item in weights}


def test_tilt_is_separate_from_frozen_r181_r182_roles_and_profiles():
    assert subject.TILT_ROLE not in frozen_targets.ROLES
    assert subject.MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION == Decimal("0.20")
    assert (
        hashlib.sha256(Path(frozen_targets.__file__).read_bytes()).hexdigest()
        == "0b280fdc1ebcb5f8ab073ff78f3008057e86db14b6254145bc5f86e18d2e5ea0"
    )
    assert runtime.require_six_universe_order_profile(
        frozen_targets.ROLE_SIGNAL,
        variant=runtime.CAP90_VARIANT,
    )["profile_sha256"] == (
        "d27c558b71d20694e803a244e89f3feb79ba5084971c8d6d8eefa7cf8ecf09f0"
    )
    assert runtime.require_six_universe_order_profile(
        frozen_targets.ROLE_MATCHED,
        variant=runtime.CAP90_VARIANT,
    )["profile_sha256"] == (
        "ab8e53adb828c5bb8cad23150d87f1ab87964887dc45e2e783a822cd754ce57a"
    )


def test_score_tilt_preserves_matched_stock_ids_etfs_sleeves_and_bands():
    snapshots = fixtures._snapshots()
    construction = _construction(snapshots)
    baseline = construction.matched_weights
    tilted = subject.tilt_matched_weights(construction, snapshots)

    assert tilted != baseline
    assert tuple((item.security_id, item.asset_kind) for item in tilted) == tuple(
        (item.security_id, item.asset_kind) for item in baseline
    )
    assert tuple(item for item in tilted if item.asset_kind == "etf") == tuple(
        item for item in baseline if item.asset_kind == "etf"
    )
    with localcontext() as context:
        context.prec = 96
        assert sum((item.weight for item in tilted), Decimal(0)) == Decimal("0.98")
        old = _by_id(baseline)
        new = _by_id(tilted)
        outer = new["sid-SPY-000"] - old["sid-SPY-000"]
        near_median = new["sid-SPY-004"] - old["sid-SPY-004"]
        assert outer > near_median > 0
        for item in baseline:
            if item.asset_kind == "stock":
                assert Decimal("0.8") * item.weight <= new[item.security_id]
                assert new[item.security_id] <= Decimal("1.2") * item.weight
                assert new[item.security_id] <= gate.DIRECT_STOCK_WEIGHT_CAP
        for sleeve in construction.sleeves:
            ids = {security_id for security_id, _ in sleeve.matched_stock_weights}
            assert sum((new[sid] for sid in ids), Decimal(0)) == sum(
                (old[sid] for sid in ids), Decimal(0)
            )
            assert new.get(sleeve.etf_security_id, Decimal(0)) == (
                sleeve.matched_etf_fallback_weight
            )


def test_missing_score_stays_at_baseline_while_other_scores_can_tilt():
    original = fixtures._snapshots()
    first = original[0]
    rows = (
        dataclasses.replace(first.constituents[0], firm_specific_score=None),
        *first.constituents[1:],
    )
    snapshots = fixtures._replace_snapshot(original, "SPY", rows)
    construction = _construction(snapshots)
    baseline = _by_id(construction.matched_weights)
    tilted = _by_id(subject.tilt_matched_weights(construction, snapshots))
    missing_id = rows[0].security_id

    assert missing_id in baseline
    assert tilted[missing_id] == baseline[missing_id]
    assert any(
        tilted[security_id] != baseline[security_id]
        for security_id, _ in construction.sleeves[0].matched_stock_weights
        if security_id != missing_id
    )


def test_tied_only_scores_leave_exact_matched_weights():
    snapshots = tuple(
        dataclasses.replace(
            snapshot,
            constituents=tuple(
                dataclasses.replace(
                    row,
                    firm_specific_score=(
                        Decimal(1)
                        if row.firm_specific_score is not None
                        and row.firm_specific_score > 0
                        else row.firm_specific_score
                    ),
                )
                for row in snapshot.constituents
            ),
        )
        for snapshot in fixtures._snapshots()
    )
    construction = _construction(snapshots)
    assert all(sleeve.matched_stock_weights for sleeve in construction.sleeves)
    assert subject.tilt_matched_weights(construction, snapshots) == (
        construction.matched_weights
    )


def test_structural_zero_scores_do_not_donate_to_one_positive_name():
    snapshots = tuple(
        dataclasses.replace(
            snapshot,
            constituents=tuple(
                dataclasses.replace(
                    row,
                    firm_specific_score=(
                        Decimal(1) if index in (0, 10, 11, 12, 13)
                        else Decimal(0)
                    ),
                )
                for index, row in enumerate(snapshot.constituents)
            ),
        )
        for snapshot in fixtures._snapshots()
    )
    construction = _construction(snapshots)
    assert all(
        len(sleeve.matched_stock_weights) == 5
        for sleeve in construction.sleeves
    )
    assert subject.tilt_matched_weights(construction, snapshots) == (
        construction.matched_weights
    )


def test_shared_stock_never_crosses_aggregate_duplicate_cap():
    snapshots = fixtures._snapshots(shared_security_id="sid-shared")
    construction = _construction(snapshots)
    baseline = construction.matched_weights
    tilted = subject.tilt_matched_weights(construction, snapshots)

    assert tuple((item.security_id, item.asset_kind) for item in tilted) == tuple(
        (item.security_id, item.asset_kind) for item in baseline
    )
    assert tuple(item for item in tilted if item.asset_kind == "etf") == tuple(
        item for item in baseline if item.asset_kind == "etf"
    )
    assert all(
        item.weight <= gate.DIRECT_STOCK_WEIGHT_CAP
        for item in tilted if item.asset_kind == "stock"
    )
    assert sum((item.weight for item in tilted), Decimal(0)) == Decimal("0.98")


def test_unavailable_sleeve_keeps_its_exact_own_etf_fallback():
    snapshots = fixtures._replace_snapshot(fixtures._snapshots(), "REMX", ())
    construction = gate.build_six_universe_construction(
        snapshots,
        gate.TOP10_CAP90_EXPLORATORY_PROFILE,
        unavailable_universe_ids=("REMX",),
    )
    tilted = subject.tilt_matched_weights(construction, snapshots)
    old = _by_id(construction.matched_weights)
    new = _by_id(tilted)

    assert new["etf-sid-REMX"] == old["etf-sid-REMX"] == (
        gate.SLEEVE_BUDGETS[4]
    )
    assert not any(sid.startswith("sid-REMX-") for sid in new)
    assert set(new) == set(old)
    with localcontext() as context:
        context.prec = 96
        assert sum((item.weight for item in tilted), Decimal(0)) == Decimal("0.98")


def test_score_snapshot_must_reproduce_same_market_cap_construction():
    snapshots = fixtures._snapshots()
    construction = _construction(snapshots)
    first = snapshots[0]
    changed = fixtures._replace_snapshot(
        snapshots,
        "SPY",
        (
            dataclasses.replace(first.constituents[0], pit_market_cap=Decimal(1)),
            *first.constituents[1:],
        ),
    )
    with pytest.raises(
        subject.MatchedRevisionTiltError,
        match="construction and score snapshot differ",
    ):
        subject.tilt_matched_weights(construction, changed)


def test_tilt_refuses_old_gate_profile():
    snapshots = fixtures._snapshots()
    old = gate.build_six_universe_construction(
        snapshots, gate.TOP10_PRIMARY_PROFILE
    )
    with pytest.raises(
        subject.MatchedRevisionTiltError,
        match="exact cap-90",
    ):
        subject.tilt_matched_weights(old, snapshots)


def test_v4_builder_captures_one_same_session_score_and_binds_matched_path():
    value = input_fixtures._input(20)
    snapshots = gate_fixtures._snapshots(value)
    matched = frozen_targets.SixUniverseOrderTargetBuilder(
        value,
        role=frozen_targets.ROLE_MATCHED,
        profile=frozen_targets.ORDER_CAP90_EVALUATION_PROFILE,
    )
    tilted = subject.MatchedRevisionTiltTargetBuilder(value)

    for index, snapshot in enumerate(snapshots, start=1):
        baseline = matched.build(snapshot.session, snapshot)
        decision = tilted.build(snapshot.session, snapshot)
        assert decision.role == subject.TILT_ROLE
        assert decision.construction_sha256 == baseline.construction_sha256
        assert decision.baseline_target_sha256 == baseline.target_sha256
        assert decision.sleeves == baseline.sleeves
        assert decision.target_weights == baseline.target_weights
        assert decision.to_record()["schema"] == subject.DECISION_TARGET_SCHEMA
        assert tilted._capture.call_count == index
        assert tilted._capture.latest is None

    baseline_path = matched.complete_path()
    path = tilted.complete_path()
    assert path.role == subject.TILT_ROLE
    assert path.baseline_target_path_sha256 == baseline_path.target_path_sha256
    assert path.construction_path_sha256 == baseline_path.construction_path_sha256
    assert path.target_path_sha256 != baseline_path.target_path_sha256
    assert path.to_record()["schema"] == subject.TARGET_PATH_SCHEMA
    assert path.to_record()["decision_count"] == 261


def test_v4_builder_refuses_stale_or_wrong_session_score():
    value = input_fixtures._input(20)
    first = gate_fixtures._snapshots(value)[0]
    stale = subject.MatchedRevisionTiltTargetBuilder(value)
    stale._capture.latest = object()
    with pytest.raises(subject.MatchedRevisionTiltError, match="stale score"):
        stale.build(first.session, first)
    assert stale.next_required_session is None

    wrong = subject.MatchedRevisionTiltTargetBuilder(value)
    original = wrong._capture._scorer.score_session

    def wrong_session(session):
        return dataclasses.replace(original(session), session="2020-12-31")

    wrong._capture._scorer.score_session = wrong_session
    with pytest.raises(subject.MatchedRevisionTiltError, match="score session"):
        wrong.build(first.session, first)
    assert wrong.next_required_session is None
