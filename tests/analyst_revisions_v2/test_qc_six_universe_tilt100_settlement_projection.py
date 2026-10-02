"""Focused guards for the distinct R193 100% settlement tilt source."""

import dataclasses
from decimal import Decimal, localcontext
import hashlib
from pathlib import Path
import sys
import types

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_delta_order_package as delta
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_gate as gate
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_settlement_qc_projection as r192,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_tilt100_qc_projection as subject,
)
from tests.analyst_revisions_v2 import (
    test_qc_accepted_risk_six_universe_gate as gate_fixtures,
)


PACKAGE_PATH = Path(
    "artifacts/analyst_revisions_v2/"
    "accepted_risk_delta_order_package_20260918_01/"
    "arv2-preliminary-qc-package-7803b84f0841f9685a4951de"
)
TARGETS_PATH = "accepted_risk_six_universe_order_tilt_targets.py"
RUNTIME_PATH = "accepted_risk_six_universe_order_tilt_qc_runtime.py"


@pytest.fixture(scope="module")
def package():
    if not PACKAGE_PATH.is_dir():
        pytest.skip("local ignored exact delta package unavailable")
    return delta.load_accepted_risk_delta_order_package(
        PACKAGE_PATH,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256,
    )


@pytest.fixture(scope="module")
def projections(package):
    return (
        r192.build_settlement_projection(package, "R192"),
        subject.build_tilt100_settlement_projection(package),
    )


def _projected_targets(projections, monkeypatch, *, predecessor=False):
    projection = projections[0] if predecessor else projections[1]
    source = next(item.source_bytes for item in projection.source_files
                  if item.project_path == TARGETS_PATH)
    module = types.ModuleType(
        "arv2_r192_projected_targets_test" if predecessor
        else "arv2_r193_projected_targets_test"
    )
    monkeypatch.setitem(sys.modules, module.__name__, module)
    exec(compile(source, TARGETS_PATH, "exec"), module.__dict__)
    return module


def test_r193_exact_closure_changes_only_target_runtime_and_main(projections):
    old, new = projections
    assert old.projection_sha256 == subject.PINNED_R192_PROJECTION_SHA256
    assert new.projection_sha256 == subject.PINNED_TILT100_PROJECTION_SHA256
    assert new.profile_sha256 == subject.PINNED_TILT100_PROFILE_SHA256
    assert new.schema == subject.PROJECTION_SCHEMA != old.schema
    assert new.role == subject.TILT100_ROLE == "matched_revision_tilt100"
    assert new.variant == subject.TILT100_VARIANT != old.variant
    assert new.total_source_byte_count == subject.PINNED_TILT100_TOTAL_SOURCE_BYTES
    assert new.total_source_byte_count <= 425_984
    assert new.package_sha256 == old.package_sha256
    assert new.activation_manifest_sha256 == old.activation_manifest_sha256
    assert new.backtest_only is True and new.market_on_open_orders_only is True
    assert not any((new.live_orders, new.paper_orders, new.funded_orders,
                    new.deployment, new.trading))
    prior = {item.project_path: item for item in old.source_files}
    current = {item.project_path: item for item in new.source_files}
    assert len(prior) == len(current) == 16
    assert set(prior) == set(current)
    assert {path for path in prior if current[path].source_bytes != prior[path].source_bytes} == {
        TARGETS_PATH, RUNTIME_PATH, "main.py",
    }
    for path in set(prior) - {TARGETS_PATH, RUNTIME_PATH, "main.py"}:
        assert current[path] == prior[path]
    assert set(current) == set(subject.PINNED_TILT100_FILE_SHA256S)
    assert set(current) == set(subject.PINNED_TILT100_FILE_BYTE_COUNTS)
    for path in current:
        assert current[path].content_sha256 == subject.PINNED_TILT100_FILE_SHA256S[path]
        assert current[path].byte_count == subject.PINNED_TILT100_FILE_BYTE_COUNTS[path]
    manifest = hashlib.sha256(subject._base._canonical(tuple(
        (item.project_path, item.content_sha256, item.byte_count)
        for item in new.source_files
    ))).hexdigest()
    assert manifest == subject.PINNED_TILT100_SOURCE_MANIFEST_SHA256
    assert (new.total_source_byte_count + subject._base.MINIMUM_REVIEW_MARGIN_BYTES
            <= subject._base.MAXIMUM_TOTAL_SOURCE_BYTES)
    for item in new.source_files:
        compile("from AlgorithmImports import *\n" + item.source_bytes.decode("ascii"),
                item.project_path, "exec")
    main = current["main.py"].source_bytes.decode("ascii")
    assert "class ARV2SixUniverseOrderTilt100Algorithm(QCAlgorithm):" in main
    assert "role='matched_revision_tilt100'," in main
    assert f"variant='{subject.TILT100_VARIANT}'," in main
    assert "self.universe_settings.leverage = 2" in main
    assert "                leverage=2,\n" in main


def test_r193_profile_preserves_r191_cash_and_order_economics():
    matched = r192.require_settlement_profile("R191")
    old = r192.require_settlement_profile("R192")
    new = subject.require_tilt100_profile()
    assert matched["profile_sha256"] == subject.PINNED_R191_PROFILE_SHA256
    assert old["matched_baseline_profile_sha256"] == new[
        "matched_baseline_profile_sha256"] == matched["profile_sha256"]
    assert new["maximum_stock_weight_change_fraction"] == "1.00"
    assert {key for key in new if new[key] != old[key]} == {
        "schema", "profile_id", "role", "target_path_schema",
        "decision_target_schema", "maximum_stock_weight_change_fraction",
        "profile_sha256",
    }
    assert new["event_cash_policy_id"] == r192.SETTLEMENT_POLICY_ID
    assert new["transient_pending_sell_cash_deficit_allowed"] is True
    assert new["settled_cash_nonnegative_required"] is True
    assert new["target_gross_exposure"] == "0.98"
    assert new["admission_leverage"] == "2"
    assert new["modeled_fee_bps_per_side"] == "10"
    assert (new["evaluation_start_session"], new["evaluation_end_session"]) == (
        "2021-01-04", "2025-12-31")


@pytest.mark.parametrize("shared_security_id", (None, "sid-shared"))
def test_r193_valid_tied_rank_transfer_preserves_selection_and_gross(
    projections, monkeypatch, shared_security_id,
):
    old_target = _projected_targets(projections, monkeypatch, predecessor=True)
    new_target = _projected_targets(projections, monkeypatch)
    # Tied low ranks retain positive weight even at the full target fraction.
    snapshots = tuple(dataclasses.replace(
        universe,
        constituents=tuple(dataclasses.replace(
            row, firm_specific_score=Decimal(2 if index == 0 else
                                             1 if index < 12 else 0))
            for index, row in enumerate(universe.constituents)),
    ) for universe in gate_fixtures._snapshots(
        shared_security_id=shared_security_id))
    construction = gate.build_six_universe_construction(
        snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
    baseline = {item.security_id: item.weight
                for item in construction.matched_weights}
    old = {item.security_id: item.weight for item in
           old_target.tilt_matched_weights(construction, snapshots)}
    new_weights = new_target.tilt_matched_weights(construction, snapshots)
    new = {item.security_id: item.weight for item in new_weights}
    assert new_target.MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION == Decimal("1.00")
    assert tuple((item.security_id, item.asset_kind) for item in new_weights) == (
        tuple((item.security_id, item.asset_kind)
              for item in construction.matched_weights))
    assert all(item.weight > 0 for item in new_weights)
    if shared_security_id is None:
        assert any(abs(new[sid] - baseline[sid]) > abs(old[sid] - baseline[sid])
                   for sid in baseline)
    for item in construction.matched_weights:
        if item.asset_kind == "stock":
            assert new[item.security_id] <= 2 * item.weight
            assert new[item.security_id] <= gate.DIRECT_STOCK_WEIGHT_CAP
        else:
            assert new[item.security_id] == item.weight
    if shared_security_id is not None:
        assert new[shared_security_id] == gate.DIRECT_STOCK_WEIGHT_CAP
    with localcontext() as context:
        context.prec = 96
        assert sum(new.values(), Decimal(0)) == Decimal("0.98")


def test_r193_zero_weight_refuses_without_relaxing_positive_cap(
    projections, monkeypatch,
):
    old_target = _projected_targets(projections, monkeypatch, predecessor=True)
    new_target = _projected_targets(projections, monkeypatch)
    snapshots = gate_fixtures._snapshots()
    construction = gate.build_six_universe_construction(
        snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
    assert old_target.tilt_matched_weights(construction, snapshots)
    with pytest.raises(new_target.MatchedRevisionTiltError,
                       match="aggregate stock cap changed"):
        new_target.tilt_matched_weights(construction, snapshots)


def test_r193_projected_runtime_profile_matches_host_pin(projections, monkeypatch):
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_order_qc_runtime as base_runtime,
        accepted_risk_six_universe_order_targets as base_targets,
    )
    files = {item.project_path: item.source_bytes for item in projections[1].source_files}
    monkeypatch.setitem(sys.modules, "accepted_risk_six_universe_order_qc_runtime",
                        base_runtime)
    monkeypatch.setitem(sys.modules, "accepted_risk_six_universe_order_targets",
                        base_targets)
    bridge = types.ModuleType("accepted_risk_six_universe_order_bridge_qc_runtime")
    monkeypatch.setitem(sys.modules, bridge.__name__, bridge)
    exec(compile(files[bridge.__name__ + ".py"], bridge.__name__, "exec"),
         bridge.__dict__)
    targets = types.ModuleType("accepted_risk_six_universe_order_tilt_targets")
    monkeypatch.setitem(sys.modules, targets.__name__, targets)
    exec(compile(files[TARGETS_PATH], TARGETS_PATH, "exec"), targets.__dict__)
    runtime = types.ModuleType("accepted_risk_six_universe_order_tilt_qc_runtime")
    monkeypatch.setitem(sys.modules, runtime.__name__, runtime)
    exec(compile(files[RUNTIME_PATH], RUNTIME_PATH, "exec"), runtime.__dict__)
    assert bridge.require_bridge_profile("matched") == r192.require_settlement_profile("R191")
    assert runtime.require_tilt_profile() == subject.require_tilt100_profile()


def test_r193_rejects_predecessor_transform_and_output_pin_drift(
    package, monkeypatch,
):
    monkeypatch.setattr(subject, "PINNED_R192_PROJECTION_SHA256", "0" * 64)
    with pytest.raises(subject.SixUniverseTilt100QcProjectionError):
        subject.build_tilt100_settlement_projection(package)
    monkeypatch.undo()
    first = subject._TRANSFORMS[TARGETS_PATH][0]
    monkeypatch.setitem(subject._TRANSFORMS, TARGETS_PATH,
                        ((first[0], first[1], first[2] + 1),
                         *subject._TRANSFORMS[TARGETS_PATH][1:]))
    with pytest.raises(subject.SixUniverseTilt100QcProjectionError):
        subject.build_tilt100_settlement_projection(package)
    monkeypatch.undo()
    monkeypatch.setattr(subject, "PINNED_TILT100_SOURCE_MANIFEST_SHA256", "0" * 64)
    with pytest.raises(subject.SixUniverseTilt100QcProjectionError):
        subject.build_tilt100_settlement_projection(package)
