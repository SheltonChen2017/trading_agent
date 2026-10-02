"""R186 80% tilt projection is a separate successor to frozen R185."""

import ast
from decimal import Decimal, localcontext
from pathlib import Path
import sys
import types

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_delta_order_package as delta,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_gate as gate,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_qc_projection as base_projection,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_qc_runtime as base_runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_bridge_qc_runtime as bridge_runtime,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_targets as base_targets,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_tilt40_qc_projection as r185_projection,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_tilt80_qc_projection as subject,
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
FROZEN_R185_PROJECTION_SHA256 = (
    "2a9f9a2175e2765c1136d4aca3d86d617bbee970769eecae6dcab2e0f1127c7d"
)
FROZEN_R185_PROFILE_SHA256 = (
    "a76cead2de5fef1176803f77b2a7efd3cc11fa24734dcdcf91a047f4ae552539"
)
FROZEN_R186_PROJECTION_SHA256 = (
    "16240a1ead1dd8466961556ffcfcfc58a6c974d763e87b72c27cfdce72699604"
)
FROZEN_R186_PROFILE_SHA256 = (
    "2fe851dd13421ea0d7d750d17ba509ee6f8407e25eb6a142725cf7c17f387036"
)


@pytest.fixture(scope="module")
def package():
    if not PACKAGE_PATH.is_dir():
        pytest.skip("local ignored delta package is unavailable on this host")
    return delta.load_accepted_risk_delta_order_package(
        PACKAGE_PATH,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256,
    )


def _projections(package):
    old = r185_projection.build_accepted_risk_six_universe_order_tilt40_qc_projection(
        package
    )
    new = subject.build_accepted_risk_six_universe_order_tilt80_qc_projection(
        package
    )
    return old, new


def _projected_targets(package, monkeypatch):
    _old, new = _projections(package)
    projected_targets = next(
        item.source_bytes for item in new.source_files
        if item.project_path == TARGETS_PATH
    )
    module = types.ModuleType("arv2_r186_projected_tilt_targets_test")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    exec(compile(projected_targets, TARGETS_PATH, "exec"), module.__dict__)
    return module


def test_r186_changes_only_three_files_and_preserves_order_source(package):
    old, new = _projections(package)
    assert old.projection_sha256 == FROZEN_R185_PROJECTION_SHA256
    assert old.profile_sha256 == FROZEN_R185_PROFILE_SHA256
    assert new.projection_sha256 == FROZEN_R186_PROJECTION_SHA256
    assert new.profile_sha256 == FROZEN_R186_PROFILE_SHA256
    assert new.total_source_byte_count == old.total_source_byte_count == 422758
    assert new.schema == subject.PROJECTION_SCHEMA
    assert new.role == subject.TILT80_ROLE == "matched_revision_tilt80"
    assert new.variant == subject.TILT80_VARIANT
    assert new.profile_sha256 == subject.require_tilt80_profile()["profile_sha256"]
    assert new.package_sha256 == old.package_sha256
    assert new.activation_manifest_sha256 == old.activation_manifest_sha256
    assert new.backtest_only is True
    assert new.market_on_open_orders_only is True
    assert not any((
        new.live_orders, new.paper_orders, new.funded_orders,
        new.deployment, new.trading,
    ))

    old_files = {item.project_path: item.source_bytes for item in old.source_files}
    new_files = {item.project_path: item.source_bytes for item in new.source_files}
    assert len(old_files) == len(new_files) == 16
    assert set(new_files) == set(old_files)
    assert {
        path for path in old_files if new_files[path] != old_files[path]
    } == {"main.py", TARGETS_PATH, RUNTIME_PATH}
    target_text = new_files[TARGETS_PATH].decode("ascii")
    runtime_text = new_files[RUNTIME_PATH].decode("ascii")
    main_text = new_files["main.py"].decode("ascii")
    assert 'MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION = Decimal("0.80")' in target_text
    assert '"maximum_stock_weight_change_fraction": "0.80"' in runtime_text
    assert "matched_revision_tilt80" in main_text
    assert subject.TILT80_VARIANT in main_text
    assert "self.universe_settings.leverage = 2" in main_text
    assert "                leverage=2,\n" in main_text
    assert "market_on_open_order" not in main_text


def test_r186_projected_files_are_prelude_safe_and_within_qc_limits(package):
    _old, new = _projections(package)
    assert new.total_source_byte_count + base_projection.MINIMUM_REVIEW_MARGIN_BYTES <= (
        base_projection.MAXIMUM_TOTAL_SOURCE_BYTES
    )
    for item in new.source_files:
        text = item.source_bytes.decode("ascii")
        assert len(text) <= base_projection.MAXIMUM_QC_SOURCE_CHARACTERS
        assert not any(
            isinstance(node, ast.ImportFrom) and node.module == "__future__"
            for node in ast.walk(ast.parse(text))
        )
        compile("from AlgorithmImports import *\n" + text, item.project_path, "exec")


def test_r186_refuses_changed_predecessor_source_and_replacement_count(
    package, monkeypatch,
):
    monkeypatch.setattr(subject, "_R185_PROJECTION_SHA256", "0" * 64)
    with pytest.raises(subject.SixUniverseTilt80QcProjectionError):
        subject.build_accepted_risk_six_universe_order_tilt80_qc_projection(package)
    monkeypatch.undo()

    monkeypatch.setitem(subject._R185_SOURCE_SHA256S, TARGETS_PATH, "0" * 64)
    with pytest.raises(subject.SixUniverseTilt80QcProjectionError):
        subject.build_accepted_risk_six_universe_order_tilt80_qc_projection(package)
    monkeypatch.undo()

    monkeypatch.setitem(subject._R186_SOURCE_SHA256S, TARGETS_PATH, "0" * 64)
    with pytest.raises(subject.SixUniverseTilt80QcProjectionError):
        subject.build_accepted_risk_six_universe_order_tilt80_qc_projection(package)
    monkeypatch.undo()

    replacements = subject._TRANSFORMS[TARGETS_PATH]
    first = replacements[0]
    monkeypatch.setitem(
        subject._TRANSFORMS,
        TARGETS_PATH,
        ((first[0], first[1], first[2] + 1), *replacements[1:]),
    )
    with pytest.raises(subject.SixUniverseTilt80QcProjectionError):
        subject.build_accepted_risk_six_universe_order_tilt80_qc_projection(package)


def test_r186_target_transfer_is_larger_but_preserves_selection_and_80_band(
    package, monkeypatch,
):
    module = _projected_targets(package, monkeypatch)
    snapshots = gate_fixtures._snapshots()
    construction = gate.build_six_universe_construction(
        snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE
    )
    baseline = {item.security_id: item.weight for item in construction.matched_weights}
    r185_module = types.ModuleType("arv2_r185_projected_tilt_targets_test")
    monkeypatch.setitem(sys.modules, r185_module.__name__, r185_module)
    old, _new = _projections(package)
    old_targets = next(
        item.source_bytes for item in old.source_files
        if item.project_path == TARGETS_PATH
    )
    exec(compile(old_targets, TARGETS_PATH, "exec"), r185_module.__dict__)
    r185_target = r185_module.tilt_matched_weights(construction, snapshots)
    r186_target = module.tilt_matched_weights(construction, snapshots)
    r185 = {item.security_id: item.weight for item in r185_target}
    r186 = {item.security_id: item.weight for item in r186_target}
    assert module.MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION == Decimal("0.80")
    assert set(r186) == set(r185) == set(baseline)
    assert tuple(
        (item.security_id, item.asset_kind) for item in r186_target
    ) == tuple(
        (item.security_id, item.asset_kind)
        for item in construction.matched_weights
    )
    assert tuple(item for item in r186_target if item.asset_kind == "etf") == (
        tuple(item for item in construction.matched_weights if item.asset_kind == "etf")
    )
    with localcontext() as context:
        context.prec = 96
        assert sum(r186.values(), Decimal(0)) == Decimal("0.98")
    assert any(
        abs(r186[sid] - baseline[sid]) > abs(r185[sid] - baseline[sid])
        for sid in baseline
    )
    for item in construction.matched_weights:
        if item.asset_kind == "stock":
            assert Decimal("0.20") * item.weight <= r186[item.security_id]
            assert r186[item.security_id] <= Decimal("1.80") * item.weight
            assert r186[item.security_id] <= gate.DIRECT_STOCK_WEIGHT_CAP
        else:
            assert r186[item.security_id] == item.weight


def test_r186_tight_duplicate_stock_cap_preserves_ids_etfs_and_gross(
    package, monkeypatch,
):
    module = _projected_targets(package, monkeypatch)
    snapshots = gate_fixtures._snapshots(shared_security_id="sid-shared")
    construction = gate.build_six_universe_construction(
        snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE
    )
    baseline = construction.matched_weights
    tilted = module.tilt_matched_weights(construction, snapshots)
    assert tuple((item.security_id, item.asset_kind) for item in tilted) == tuple(
        (item.security_id, item.asset_kind) for item in baseline
    )
    assert tuple(item for item in tilted if item.asset_kind == "etf") == tuple(
        item for item in baseline if item.asset_kind == "etf"
    )
    shared = next(item for item in tilted if item.security_id == "sid-shared")
    baseline_shared = next(item for item in baseline if item.security_id == "sid-shared")
    assert shared.weight == baseline_shared.weight == gate.DIRECT_STOCK_WEIGHT_CAP
    assert all(
        item.weight <= gate.DIRECT_STOCK_WEIGHT_CAP
        for item in tilted if item.asset_kind == "stock"
    )
    assert sum((item.weight for item in tilted), Decimal(0)) == Decimal("0.98")


def test_r186_transfer_behavior_distinguishes_a_40_percent_reversion(
    package, monkeypatch,
):
    module = _projected_targets(package, monkeypatch)
    snapshots = gate_fixtures._snapshots()
    construction = gate.build_six_universe_construction(
        snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE
    )
    baseline = {item.security_id: item.weight for item in construction.matched_weights}
    actual = {
        item.security_id: item.weight
        for item in module.tilt_matched_weights(construction, snapshots)
    }
    monkeypatch.setattr(
        module, "MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION", Decimal("0.40")
    )
    reverted = {
        item.security_id: item.weight
        for item in module.tilt_matched_weights(construction, snapshots)
    }
    assert any(
        abs(actual[sid] - baseline[sid]) > abs(reverted[sid] - baseline[sid])
        for sid in baseline
    )


def test_projected_runtime_profile_matches_host_r186_profile(package, monkeypatch):
    _old, new = _projections(package)
    files = {item.project_path: item.source_bytes for item in new.source_files}
    target_module = types.ModuleType("accepted_risk_six_universe_order_tilt_targets")
    runtime_module = types.ModuleType("accepted_risk_six_universe_order_tilt_qc_runtime")
    monkeypatch.setitem(sys.modules, target_module.__name__, target_module)
    monkeypatch.setitem(sys.modules, runtime_module.__name__, runtime_module)
    monkeypatch.setitem(
        sys.modules, "accepted_risk_six_universe_order_qc_runtime", base_runtime,
    )
    monkeypatch.setitem(
        sys.modules, "accepted_risk_six_universe_order_bridge_qc_runtime",
        bridge_runtime,
    )
    monkeypatch.setitem(
        sys.modules, "accepted_risk_six_universe_order_targets", base_targets,
    )
    exec(compile(files[TARGETS_PATH], TARGETS_PATH, "exec"), target_module.__dict__)
    exec(compile(files[RUNTIME_PATH], RUNTIME_PATH, "exec"), runtime_module.__dict__)

    projected_profile = runtime_module.require_tilt_profile()
    assert projected_profile == subject.require_tilt80_profile()
    assert projected_profile["profile_sha256"] == FROZEN_R186_PROFILE_SHA256
    assert projected_profile["maximum_stock_weight_change_fraction"] == "0.80"
    assert projected_profile["role"] == "matched_revision_tilt80"
