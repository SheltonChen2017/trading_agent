"""Focused behavioral and exact-source guards for the R195-R200 tilt ladder."""

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
    accepted_risk_six_universe_order_tilt100_floor_qc_projection as r194,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_tilt_ladder_floor_qc_projection as subject,
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
CHANGED_PATHS = {
    TARGETS_PATH, "accepted_risk_six_universe_order_tilt_qc_runtime.py", "main.py",
}


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
    return {
        percent: subject.build_tilt_floor_projection(package, percent)
        for percent in subject.CANDIDATE_IDS
    }


def _projected_targets(source, monkeypatch, name):
    module = types.ModuleType(name)
    monkeypatch.setitem(sys.modules, name, module)
    exec(compile(source, TARGETS_PATH, "exec"), module.__dict__)
    return module


def _target_source(projection):
    return next(item.source_bytes.decode("ascii") for item in projection.source_files
                if item.project_path == TARGETS_PATH)


def _tilt_and_capture_sleeves(module, source, construction, snapshots):
    """Observe exact projected function locals at its per-sleeve budget check."""
    line = next(index for index, value in enumerate(source.splitlines(), 1)
                if "_sum(updated.values()) != _sum(baseline.values())" in value)
    captured = []

    def trace(frame, event, argument):
        if (event == "line" and frame.f_code.co_name == "tilt_matched_weights"
                and frame.f_code.co_filename == TARGETS_PATH
                and frame.f_lineno == line):
            captured.append((frame.f_locals["sleeve"].universe_id,
                             dict(frame.f_locals["baseline"]),
                             dict(frame.f_locals["updated"])))
        return trace

    previous = sys.gettrace()
    sys.settrace(trace)
    try:
        tilted = module.tilt_matched_weights(construction, snapshots)
    finally:
        sys.settrace(previous)
    return tilted, captured


def _shared_worst_donor_snapshots():
    return tuple(dataclasses.replace(
        snapshot,
        constituents=tuple(dataclasses.replace(
            row,
            firm_specific_score=(Decimal("-1") if index == 0
                                 else row.firm_specific_score),
        ) for index, row in enumerate(snapshot.constituents)),
    ) for snapshot in gate_fixtures._snapshots(shared_security_id="sid-shared"))


def test_exact_ladder_pins_and_frozen_r194(package, projections):
    old = r194.build_tilt100_floor_projection(package)
    old_files = {item.project_path: item for item in old.source_files}
    assert old.projection_sha256 == r194.PINNED_PROJECTION_SHA256
    assert old.profile_sha256 == r194.PINNED_PROFILE_SHA256
    assert subject.CANDIDATE_IDS == {
        100: "R195", 120: "R196", 140: "R197",
        160: "R198", 180: "R199", 200: "R200",
    }
    for percent, projection in projections.items():
        profile = subject.require_tilt_floor_profile(percent)
        assert projection == subject.build_tilt_floor_projection(package, percent)
        assert projection.projection_sha256 == subject.PINNED_PROJECTION_SHA256S[percent]
        assert projection.profile_sha256 == subject.PINNED_PROFILE_SHA256S[percent]
        assert projection.total_source_byte_count == 425_975
        assert projection.total_source_byte_count == subject.PINNED_TOTAL_SOURCE_BYTES[percent]
        assert (projection.total_source_byte_count
                + subject._base.MINIMUM_REVIEW_MARGIN_BYTES
                <= subject._base.MAXIMUM_TOTAL_SOURCE_BYTES)
        assert projection.role == subject.TILT_ROLES[percent]
        assert projection.variant == subject.TILT_VARIANTS[percent]
        assert projection.schema == subject.PROJECTION_SCHEMAS[percent]
        assert projection.profile_id == subject.PROFILE_IDS[percent]
        assert projection.backtest_only is True
        assert projection.market_on_open_orders_only is True
        assert not any((projection.live_orders, projection.paper_orders,
                        projection.funded_orders, projection.deployment,
                        projection.trading))
        assert profile["profile_sha256"] == projection.profile_sha256
        assert profile["maximum_stock_weight_change_fraction"] == (
            f"{percent // 100}.{percent % 100:02d}"
        )
        assert profile["minimum_stock_and_sleeve_residual_weight"] == "1e-30"
        assert "minimum_stock_residual_weight" not in profile
        assert profile["target_gross_exposure"] == "0.98"
        files = {item.project_path: item for item in projection.source_files}
        assert len(files) == 16 and set(files) == set(old_files)
        assert {path for path in files if files[path] != old_files[path]} == CHANGED_PATHS
        expected_hashes = {
            **r194.PINNED_FILE_SHA256S,
            **subject.PINNED_CHANGED_FILE_SHA256S[percent],
        }
        expected_sizes = {
            **r194.PINNED_FILE_BYTE_COUNTS,
            **subject.PINNED_CHANGED_FILE_BYTE_COUNTS[percent],
        }
        for path, item in files.items():
            assert item.content_sha256 == expected_hashes[path]
            assert item.byte_count == expected_sizes[path] == len(item.source_bytes)
            assert hashlib.sha256(item.source_bytes).hexdigest() == item.content_sha256
        manifest = hashlib.sha256(subject._base._canonical(tuple(
            (item.project_path, item.content_sha256, item.byte_count)
            for item in projection.source_files
        ))).hexdigest()
        assert manifest == subject.PINNED_SOURCE_MANIFEST_SHA256S[percent]
    assert r194.build_tilt100_floor_projection(package) == old


def test_projected_runtime_profiles_match_host_pins(projections, monkeypatch):
    from research.analyst_revisions_v2_qc import (
        accepted_risk_six_universe_order_qc_runtime as base_runtime,
        accepted_risk_six_universe_order_targets as base_targets,
    )

    monkeypatch.setitem(sys.modules, "accepted_risk_six_universe_order_qc_runtime",
                        base_runtime)
    monkeypatch.setitem(sys.modules, "accepted_risk_six_universe_order_targets",
                        base_targets)
    for percent, projection in projections.items():
        files = {item.project_path: item.source_bytes
                 for item in projection.source_files}
        bridge = types.ModuleType("accepted_risk_six_universe_order_bridge_qc_runtime")
        monkeypatch.setitem(sys.modules, bridge.__name__, bridge)
        exec(compile(files[bridge.__name__ + ".py"], bridge.__name__, "exec"),
             bridge.__dict__)
        targets = _projected_targets(
            _target_source(projection), monkeypatch,
            "accepted_risk_six_universe_order_tilt_targets",
        )
        runtime = types.ModuleType("accepted_risk_six_universe_order_tilt_qc_runtime")
        monkeypatch.setitem(sys.modules, runtime.__name__, runtime)
        exec(compile(files[runtime.__name__ + ".py"], runtime.__name__, "exec"),
             runtime.__dict__)
        assert runtime.require_tilt_profile() == subject.require_tilt_floor_profile(percent)
        assert targets.TILT_ROLE == subject.TILT_ROLES[percent]
        assert runtime.TILT_VARIANT == subject.TILT_VARIANTS[percent]


def test_ladder_rules_are_distinct_when_room_remains_and_keep_every_sleeve_positive(
    projections, monkeypatch,
):
    unique = gate_fixtures._snapshots()
    shared = _shared_worst_donor_snapshots()
    for snapshots in (unique, shared):
        construction = gate.build_six_universe_construction(
            snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
        baseline = {item.security_id: item for item in construction.matched_weights}
        results = {}
        for percent, projection in projections.items():
            source = _target_source(projection)
            module = _projected_targets(
                source, monkeypatch, f"arv2_r{subject.CANDIDATE_IDS[percent]}_target"
                + ("_shared" if snapshots is shared else "_unique"),
            )
            assert module.MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION == Decimal(percent) / 100
            assert module.TILT_ROLE == subject.TILT_ROLES[percent]
            tilted, sleeves = _tilt_and_capture_sleeves(
                module, source, construction, snapshots)
            assert len(sleeves) == 6
            assert tuple((item.security_id, item.asset_kind) for item in tilted) == tuple(
                (item.security_id, item.asset_kind)
                for item in construction.matched_weights)
            assert all(item.weight.is_finite() and item.weight > 0 for item in tilted)
            assert all(item.weight <= gate.DIRECT_STOCK_WEIGHT_CAP
                       for item in tilted if item.asset_kind == "stock")
            assert all(item == baseline[item.security_id]
                       for item in tilted if item.asset_kind == "etf")
            with localcontext() as context:
                context.prec = 96
                assert sum((item.weight for item in tilted), Decimal(0)) == Decimal("0.98")
                for _, before, after in sleeves:
                    assert set(after) == set(before)
                    assert all(weight >= module.WEIGHT_TRANSFER_QUANTUM
                               for weight in after.values())
                    assert sum(after.values(), Decimal(0)) == sum(before.values(), Decimal(0))
            results[percent] = {item.security_id: item.weight for item in tilted}
        assert any(results[100][sid] != results[120][sid] for sid in results[100])
        assert any(results[120][sid] != results[140][sid] for sid in results[100])
        for lower, higher in ((140, 160), (160, 180), (180, 200)):
            assert any(results[lower][sid] != results[higher][sid]
                       for sid in results[lower])


def test_old_100_120_140_projection_identities_remain_frozen(projections):
    # These literal historical identities do not derive from the new pin tables.
    assert {percent: projections[percent].projection_sha256
            for percent in (100, 120, 140)} == {
        100: "c20e2c13ef477e4c1619cb93aafb4fef58c2a36c95f5a514c62d015f5722e28d",
        120: "f8489764d1925f93ecd13092d5ef0d916f681385a12dc817f02115f66328f82e",
        140: "c3edcd8bae80446fd564e4d21a1a8ff3c8a35ee68af914b13de2a344ab596576",
    }


def test_higher_capacity_may_saturate_without_forcing_a_target_change(
    projections, monkeypatch,
):
    snapshots = gate_fixtures._snapshots(positive_count=2)
    construction = gate.build_six_universe_construction(
        snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
    results = []
    for percent in (160, 180, 200):
        source = _target_source(projections[percent])
        module = _projected_targets(source, monkeypatch, f"arv2_saturation_{percent}")
        tilted, sleeves = _tilt_and_capture_sleeves(
            module, source, construction, snapshots)
        with localcontext() as context:
            context.prec = 96
            assert sum((item.weight for item in tilted), Decimal(0)) == Decimal("0.98")
            for _, before, after in sleeves:
                assert all(weight >= module.WEIGHT_TRANSFER_QUANTUM
                           for weight in after.values())
                assert min(after.values()) == module.WEIGHT_TRANSFER_QUANTUM
                assert sum(after.values(), Decimal(0)) == sum(before.values(), Decimal(0))
        results.append(tilted)
    assert results[0] == results[1] == results[2]


def test_per_sleeve_guard_is_load_bearing_on_shared_worst_donor(
    projections, monkeypatch,
):
    snapshots = _shared_worst_donor_snapshots()
    construction = gate.build_six_universe_construction(
        snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
    safe = (
        "moved = min(room, available, updated[donor_id] - WEIGHT_TRANSFER_QUANTUM, "
        "stock_totals[donor_id] - WEIGHT_TRANSFER_QUANTUM)"
    )
    aggregate_only = (
        "moved = min(room, available, stock_totals[donor_id] "
        "- WEIGHT_TRANSFER_QUANTUM)"
    )
    for percent, projection in projections.items():
        source = _target_source(projection)
        assert source.count(safe) == 1
        mutant_source = source.replace(safe, aggregate_only)
        mutant = _projected_targets(
            mutant_source, monkeypatch, f"arv2_r{subject.CANDIDATE_IDS[percent]}_mutant")
        tilted, sleeves = _tilt_and_capture_sleeves(
            mutant, mutant_source, construction, snapshots)
        assert all(item.weight > 0 for item in tilted)
        assert any(after["sid-shared"] <= 0 for _, _, after in sleeves)


@pytest.mark.parametrize("percent", (True, 0, 99, 101, 220, "120", None))
def test_only_exact_pinned_ladder_candidates_are_admitted(package, percent):
    with pytest.raises(subject.SixUniverseTiltLadderFloorQcProjectionError,
                       match="100, 120, 140, 160, 180, or 200"):
        subject.build_tilt_floor_projection(package, percent)
    with pytest.raises(subject.SixUniverseTiltLadderFloorQcProjectionError,
                       match="100, 120, 140, 160, 180, or 200"):
        subject.require_tilt_floor_profile(percent)


def test_output_pin_drift_refuses(package, monkeypatch):
    monkeypatch.setitem(subject.PINNED_PROJECTION_SHA256S, 120, "0" * 64)
    with pytest.raises(subject.SixUniverseTiltLadderFloorQcProjectionError,
                       match="exact pin"):
        subject.build_tilt_floor_projection(package, 120)
