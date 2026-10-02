"""Focused red/green proof for R194's distinct positive-residual tilt."""

import ast
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
    accepted_risk_six_universe_order_tilt100_qc_projection as r193,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_tilt100_floor_qc_projection as subject,
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
        r193.build_tilt100_settlement_projection(package),
        subject.build_tilt100_floor_projection(package),
    )


def _projected_targets(projection, monkeypatch, name):
    source = next(item.source_bytes for item in projection.source_files
                  if item.project_path == TARGETS_PATH)
    module = types.ModuleType(name)
    monkeypatch.setitem(sys.modules, name, module)
    exec(compile(source, TARGETS_PATH, "exec"), module.__dict__)
    return module


def test_r194_exact_source_is_separately_pinned_and_r193_remains_unchanged(
    package, projections,
):
    old, new = projections
    assert old == r193.build_tilt100_settlement_projection(package)
    assert old.projection_sha256 == subject.PINNED_R193_PROJECTION_SHA256
    assert old.profile_sha256 == subject.PINNED_R193_PROFILE_SHA256
    assert new.projection_sha256 == subject.PINNED_PROJECTION_SHA256
    assert new.profile_sha256 == subject.PINNED_PROFILE_SHA256
    assert new.schema == subject.PROJECTION_SCHEMA != old.schema
    assert new.role == subject.TILT_ROLE != old.role
    assert new.variant == subject.TILT_VARIANT != old.variant
    assert new.total_source_byte_count == subject.PINNED_TOTAL_SOURCE_BYTES == 425_919
    assert new.total_source_byte_count <= 425_984
    assert new.package_sha256 == old.package_sha256
    assert new.activation_manifest_sha256 == old.activation_manifest_sha256
    assert new.backtest_only is True and new.market_on_open_orders_only is True
    assert not any((new.live_orders, new.paper_orders, new.funded_orders,
                    new.deployment, new.trading))
    prior = {item.project_path: item for item in old.source_files}
    current = {item.project_path: item for item in new.source_files}
    assert len(prior) == len(current) == 16
    assert set(prior) == set(current) == set(subject.PINNED_FILE_SHA256S)
    assert set(current) == set(subject.PINNED_FILE_BYTE_COUNTS)
    assert {path for path in current if current[path] != prior[path]} == {
        TARGETS_PATH, RUNTIME_PATH, "main.py",
    }
    for path, item in current.items():
        assert item.content_sha256 == subject.PINNED_FILE_SHA256S[path]
        assert item.byte_count == subject.PINNED_FILE_BYTE_COUNTS[path]
        assert hashlib.sha256(item.source_bytes).hexdigest() == item.content_sha256
        assert len(item.source_bytes) == item.byte_count
    manifest = hashlib.sha256(subject._base._canonical(tuple(
        (item.project_path, item.content_sha256, item.byte_count)
        for item in new.source_files
    ))).hexdigest()
    assert manifest == subject.PINNED_SOURCE_MANIFEST_SHA256
    assert (new.total_source_byte_count + subject._base.MINIMUM_REVIEW_MARGIN_BYTES
            <= subject._base.MAXIMUM_TOTAL_SOURCE_BYTES)


def test_r194_profile_discloses_exact_floor_and_preserves_economics():
    old = r193.require_tilt100_profile()
    new = subject.require_tilt100_floor_profile()
    assert new["minimum_stock_residual_weight"] == "1e-30"
    assert new["weight_transfer_quantum"] == old["weight_transfer_quantum"]
    assert new["maximum_stock_weight_change_fraction"] == "1.00"
    assert {key for key in new if new[key] != old.get(key)} == {
        "schema", "profile_id", "role", "target_path_schema",
        "decision_target_schema", "minimum_stock_residual_weight",
        "profile_sha256",
    }
    assert new["matched_baseline_profile_sha256"] == old[
        "matched_baseline_profile_sha256"]
    for key in (
        "evaluation_start_session", "evaluation_end_session", "decision_count",
        "target_gross_exposure", "modeled_fee_bps_per_side", "admission_leverage",
        "event_cash_policy_id", "settled_cash_nonnegative_required",
    ):
        assert new[key] == old[key]


def test_r194_zero_donor_is_red_under_r193_and_green_with_residual_floor(
    projections, monkeypatch,
):
    old = _projected_targets(projections[0], monkeypatch, "arv2_r193_red_target")
    new = _projected_targets(projections[1], monkeypatch, "arv2_r194_green_target")
    snapshots = gate_fixtures._snapshots()
    construction = gate.build_six_universe_construction(
        snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
    with pytest.raises(old.MatchedRevisionTiltError,
                       match="aggregate stock cap changed"):
        old.tilt_matched_weights(construction, snapshots)
    tilted = new.tilt_matched_weights(construction, snapshots)
    assert new.MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION == Decimal("1.00")
    assert tuple((item.security_id, item.asset_kind) for item in tilted) == tuple(
        (item.security_id, item.asset_kind)
        for item in construction.matched_weights
    )
    weights = {item.security_id: item.weight for item in tilted}
    assert all(weight.is_finite() and weight > 0 for weight in weights.values())
    assert min(weights.values()) == Decimal("1e-30")
    with localcontext() as context:
        context.prec = 96
        assert sum(weights.values(), Decimal(0)) == Decimal("0.98")
        for sleeve in construction.sleeves:
            selected = set(sleeve.matched_security_ids)
            assert sum((weights[sid] for sid in selected), Decimal(0)) == sum(
                (weight for _, weight in sleeve.matched_stock_weights), Decimal(0)
            )
    original = {item.security_id: item for item in construction.matched_weights}
    for item in tilted:
        if item.asset_kind == "stock":
            assert item.weight <= gate.DIRECT_STOCK_WEIGHT_CAP
            assert item.weight <= 2 * original[item.security_id].weight
        else:
            assert item == original[item.security_id]


def test_r194_floor_guard_is_load_bearing_under_single_guard_mutation(
    projections, monkeypatch,
):
    source = next(item.source_bytes.decode("ascii")
                  for item in projections[1].source_files
                  if item.project_path == TARGETS_PATH)
    guarded = (
        "moved = min(room, available, stock_totals[donor_id] "
        "- WEIGHT_TRANSFER_QUANTUM)"
    )
    assert source.count(guarded) == 1
    mutant = types.ModuleType("arv2_r194_without_floor_mutant")
    monkeypatch.setitem(sys.modules, mutant.__name__, mutant)
    exec(compile(source.replace(guarded, "moved = min(room, available)"),
                 TARGETS_PATH, "exec"), mutant.__dict__)
    snapshots = gate_fixtures._snapshots()
    construction = gate.build_six_universe_construction(
        snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
    with pytest.raises(mutant.MatchedRevisionTiltError,
                       match="aggregate stock cap changed"):
        mutant.tilt_matched_weights(construction, snapshots)


@pytest.mark.parametrize(
    ("room", "available", "stock_total"),
    (
        ("0.5", "0.4", "0.3"),
        ("0.5", "0.4", "0.000000000000000000000000000002"),
        ("0.5", "0.4", "0.000000000000000000000000000001"),
        ("0.5", "0", "0.3"),
        ("0", "0.4", "0.3"),
        ("0.1", "0.2", "0.3"),
    ),
)
def test_r194_compact_transfer_matches_mia_nested_min(
    projections, room, available, stock_total,
):
    source = next(item.source_bytes.decode("ascii")
                  for item in projections[1].source_files
                  if item.project_path == TARGETS_PATH)
    moved = [node for node in ast.walk(ast.parse(source))
             if isinstance(node, ast.Assign)
             and len(node.targets) == 1
             and isinstance(node.targets[0], ast.Name)
             and node.targets[0].id == "moved"]
    assert len(moved) == 1
    # Evaluate the actual projected expression, not a handwritten copy. A
    # mutation to omit the donor residual fails the near-floor examples.
    expression = compile(ast.Expression(moved[0].value), "r194_moved", "eval")
    remaining = Decimal(stock_total)
    capacity = Decimal(available)
    receiver_room = Decimal(room)
    quantum = Decimal("1e-30")
    actual = eval(expression, {
        "min": min, "WEIGHT_TRANSFER_QUANTUM": quantum,
    }, {
        "room": receiver_room,
        "available": capacity,
        "stock_totals": {"donor": remaining},
        "donor_id": "donor",
    })
    mia = min(receiver_room, min(capacity, remaining - quantum))
    assert actual == mia
    assert actual >= 0


def test_r194_shared_security_remains_under_aggregate_stock_cap(
    projections, monkeypatch,
):
    target = _projected_targets(projections[1], monkeypatch, "arv2_r194_shared_target")
    snapshots = tuple(dataclasses.replace(
        universe,
        constituents=tuple(dataclasses.replace(
            row, firm_specific_score=Decimal(2 if index == 0 else
                                             1 if index < 12 else 0))
            for index, row in enumerate(universe.constituents)),
    ) for universe in gate_fixtures._snapshots(shared_security_id="sid-shared"))
    construction = gate.build_six_universe_construction(
        snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
    tilted = target.tilt_matched_weights(construction, snapshots)
    assert tuple((item.security_id, item.asset_kind) for item in tilted) == tuple(
        (item.security_id, item.asset_kind)
        for item in construction.matched_weights
    )
    shared = next(item for item in tilted if item.security_id == "sid-shared")
    assert shared.weight == gate.DIRECT_STOCK_WEIGHT_CAP
    assert all(item.weight > 0 for item in tilted)


@pytest.mark.parametrize("bad_weight", (Decimal("-1"), Decimal("NaN"),
                                         Decimal("Infinity")))
def test_r194_refuses_negative_or_nonfinite_baseline_weight(
    projections, monkeypatch, bad_weight,
):
    target = _projected_targets(projections[1], monkeypatch, "arv2_r194_bad_target")
    snapshots = gate_fixtures._snapshots()
    construction = gate.build_six_universe_construction(
        snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
    rows = list(construction.matched_weights)
    index = next(i for i, item in enumerate(rows) if item.asset_kind == "stock")
    rows[index] = dataclasses.replace(rows[index], weight=bad_weight)
    hostile = dataclasses.replace(construction, matched_weights=tuple(rows))
    with pytest.raises((gate.SixUniverseGateError, target.MatchedRevisionTiltError)):
        target.tilt_matched_weights(hostile, snapshots)


def test_r194_projected_runtime_profile_matches_host_pin(projections, monkeypatch):
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
    assert runtime.require_tilt_profile() == subject.require_tilt100_floor_profile()
    assert targets.TILT_ROLE == subject.TILT_ROLE
    assert runtime.TILT_VARIANT == subject.TILT_VARIANT


def test_r194_host_module_import_has_no_top_level_io_surface():
    source = Path(subject.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {alias.name.partition(".")[0] for node in tree.body
               if isinstance(node, ast.Import) for alias in node.names}
    assert imports == {"dataclasses", "hashlib", "json"}
    assert all(isinstance(node, (ast.Expr, ast.Import, ast.ImportFrom,
                                 ast.ClassDef, ast.Assign, ast.FunctionDef))
               for node in tree.body)
    assert all(isinstance(node.value, ast.Constant)
               for node in tree.body if isinstance(node, ast.Expr))
    assert not any(isinstance(nested, ast.Call)
                   for node in tree.body if isinstance(node, ast.Assign)
                   for nested in ast.walk(node.value))


def test_r194_rejects_predecessor_or_output_pin_drift(package, monkeypatch):
    monkeypatch.setattr(subject, "PINNED_R193_PROJECTION_SHA256", "0" * 64)
    with pytest.raises(subject.SixUniverseTilt100FloorQcProjectionError):
        subject.build_tilt100_floor_projection(package)
    monkeypatch.undo()
    first = subject._TRANSFORMS[TARGETS_PATH][0]
    monkeypatch.setitem(subject._TRANSFORMS, TARGETS_PATH,
                        ((first[0], first[1], first[2] + 1),
                         *subject._TRANSFORMS[TARGETS_PATH][1:]))
    with pytest.raises(subject.SixUniverseTilt100FloorQcProjectionError):
        subject.build_tilt100_floor_projection(package)
    monkeypatch.undo()
    monkeypatch.setattr(subject, "PINNED_SOURCE_MANIFEST_SHA256", "0" * 64)
    with pytest.raises(subject.SixUniverseTilt100FloorQcProjectionError):
        subject.build_tilt100_floor_projection(package)
