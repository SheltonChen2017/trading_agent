"""Isolated R187/R188/R189 source and economics pins, not return evidence."""

import ast
from decimal import Decimal, localcontext
from pathlib import Path
import sys
import types

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_delta_order_package as delta
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_gate as gate
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_qc_projection as base_projection,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_tilt40_qc_projection as r185,
)
from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_tilt_ladder_qc_projection as subject,
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
SOURCE_PINS = {
    70: (
        "3203481571307cbad000153542ac9529cb1e4a3ac1bac030f18150b6a22dcbe0",
        "6189373282c0e5652bda0317d0133e1ccc52057116035ed6a51428788d8e31f2",
    ),
    60: (
        "3eed978da51ef82b0de3f44b2f3bb30311e27a8f628ed3f9b6663d902f78fc55",
        "82592bb4c82078496899f2e225c31f6c47a759b93997f464fac731eff99ed875",
    ),
    50: (
        "e1f417b2a7e785e558ec0af83297083fa07c0bbc22c930447bb6e0e99a25f2d3",
        "5314cab14e8f50e38998c07dead583eb38b57eefcb0e2ad8768d5681adec116e",
    ),
}


@pytest.fixture(scope="module")
def package():
    if not PACKAGE_PATH.is_dir():
        pytest.skip("local ignored delta package is unavailable on this host")
    return delta.load_accepted_risk_delta_order_package(
        PACKAGE_PATH,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256,
    )


def _sources(package, percent):
    baseline = r185.build_accepted_risk_six_universe_order_tilt40_qc_projection(
        package
    )
    candidate = subject.build_tilt_ladder_projection(package, percent)
    return (
        baseline,
        candidate,
        {item.project_path: item.source_bytes for item in baseline.source_files},
        {item.project_path: item.source_bytes for item in candidate.source_files},
    )


@pytest.mark.parametrize("percent", subject.PERCENTS)
def test_each_candidate_is_exactly_pinned_and_changes_only_three_cloud_files(
    package, percent,
):
    baseline, candidate, old_files, new_files = _sources(package, percent)
    assert candidate.projection_sha256 == SOURCE_PINS[percent][0]
    assert candidate.profile_sha256 == SOURCE_PINS[percent][1]
    assert candidate.projection_sha256 == subject.PINNED_PROJECTIONS[percent]
    assert candidate.profile_sha256 == subject.PINNED_PROFILES[percent]
    assert candidate.total_source_byte_count == baseline.total_source_byte_count == 422758
    assert candidate.profile_sha256 == subject.require_tilt_ladder_profile(
        percent
    )["profile_sha256"]
    assert candidate.package_sha256 == baseline.package_sha256
    assert candidate.activation_manifest_sha256 == baseline.activation_manifest_sha256
    assert candidate.backtest_only is True
    assert candidate.market_on_open_orders_only is True
    assert not any((
        candidate.live_orders, candidate.paper_orders, candidate.funded_orders,
        candidate.deployment, candidate.trading,
    ))
    assert len(old_files) == len(new_files) == 16
    assert set(new_files) == set(old_files)
    assert {path for path in old_files if old_files[path] != new_files[path]} == {
        "main.py", TARGETS_PATH, RUNTIME_PATH,
    }
    target_text = new_files[TARGETS_PATH].decode("ascii")
    runtime_text = new_files[RUNTIME_PATH].decode("ascii")
    main_text = new_files["main.py"].decode("ascii")
    fraction = f"0.{percent:02d}"
    assert f'MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION = Decimal("{fraction}")' in target_text
    assert f'"maximum_stock_weight_change_fraction": "{fraction}"' in runtime_text
    assert f"matched_revision_tilt{percent}" in main_text
    assert f"cap90_matched_revision_tilt{percent}_admission_bridge_v1" in main_text
    assert "self.universe_settings.leverage = 2" in main_text
    assert "                leverage=2,\n" in main_text
    assert "market_on_open_order" not in main_text


@pytest.mark.parametrize("percent", subject.PERCENTS)
def test_each_cloud_file_compiles_with_qc_prelude(package, percent):
    _baseline, candidate, _old_files, new_files = _sources(package, percent)
    assert candidate.total_source_byte_count + base_projection.MINIMUM_REVIEW_MARGIN_BYTES <= (
        base_projection.MAXIMUM_TOTAL_SOURCE_BYTES
    )
    for path, source in new_files.items():
        text = source.decode("ascii")
        assert len(text) <= base_projection.MAXIMUM_QC_SOURCE_CHARACTERS
        assert not any(
            isinstance(node, ast.ImportFrom) and node.module == "__future__"
            for node in ast.walk(ast.parse(text))
        )
        compile("from AlgorithmImports import *\n" + text, path, "exec")


@pytest.mark.parametrize("percent", subject.PERCENTS)
def test_stock_set_etf_fallback_gross_and_caps_are_unchanged(package, percent, monkeypatch):
    _baseline, _candidate, _old_files, new_files = _sources(package, percent)
    projected = types.ModuleType(f"arv2_r{257-percent}_projected_tilt_targets_test")
    monkeypatch.setitem(sys.modules, projected.__name__, projected)
    exec(compile(new_files[TARGETS_PATH], TARGETS_PATH, "exec"), projected.__dict__)
    snapshots = gate_fixtures._snapshots(shared_security_id="sid-shared")
    construction = gate.build_six_universe_construction(
        snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE,
    )
    baseline = construction.matched_weights
    tilted = projected.tilt_matched_weights(construction, snapshots)
    assert projected.MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION == Decimal(
        f"0.{percent:02d}"
    )
    assert tuple((item.security_id, item.asset_kind) for item in tilted) == tuple(
        (item.security_id, item.asset_kind) for item in baseline
    )
    assert tuple(item for item in tilted if item.asset_kind == "etf") == tuple(
        item for item in baseline if item.asset_kind == "etf"
    )
    with localcontext() as context:
        context.prec = 96
        assert sum((item.weight for item in tilted), Decimal(0)) == Decimal("0.98")
    assert all(
        item.weight <= gate.DIRECT_STOCK_WEIGHT_CAP
        for item in tilted if item.asset_kind == "stock"
    )
    baseline_shared = next(item for item in baseline if item.security_id == "sid-shared")
    tilted_shared = next(item for item in tilted if item.security_id == "sid-shared")
    assert tilted_shared.weight == baseline_shared.weight == gate.DIRECT_STOCK_WEIGHT_CAP


@pytest.mark.parametrize("percent", subject.PERCENTS)
def test_fraction_behavior_is_distinct_from_40_and_refuses_red_mutation(
    package, percent, monkeypatch,
):
    _baseline, _candidate, _old_files, new_files = _sources(package, percent)
    projected = types.ModuleType(f"arv2_r{257-percent}_fraction_mutation_test")
    monkeypatch.setitem(sys.modules, projected.__name__, projected)
    exec(compile(new_files[TARGETS_PATH], TARGETS_PATH, "exec"), projected.__dict__)
    snapshots = gate_fixtures._snapshots()
    construction = gate.build_six_universe_construction(
        snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE,
    )
    baseline = {item.security_id: item.weight for item in construction.matched_weights}
    actual = {
        item.security_id: item.weight
        for item in projected.tilt_matched_weights(construction, snapshots)
    }
    monkeypatch.setattr(projected, "MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION", Decimal("0.40"))
    reverted = {
        item.security_id: item.weight
        for item in projected.tilt_matched_weights(construction, snapshots)
    }
    assert any(
        abs(actual[sid] - baseline[sid]) > abs(reverted[sid] - baseline[sid])
        for sid in baseline
    )
    for item in construction.matched_weights:
        if item.asset_kind == "stock":
            lo = (Decimal(1) - Decimal(f"0.{percent:02d}")) * item.weight
            hi = (Decimal(1) + Decimal(f"0.{percent:02d}")) * item.weight
            assert lo <= actual[item.security_id] <= hi


@pytest.mark.parametrize("percent", subject.PERCENTS)
def test_source_identity_and_count_mutations_refuse_before_projection(
    package, percent, monkeypatch,
):
    monkeypatch.setattr(subject, "_R185_PROJECTION_SHA256", "0" * 64)
    with pytest.raises(subject.SixUniverseTiltLadderQcProjectionError):
        subject.build_tilt_ladder_projection(package, percent)
    monkeypatch.undo()

    monkeypatch.setitem(subject._r185._R185_SOURCE_SHA256S, TARGETS_PATH, "0" * 64)
    with pytest.raises(subject.SixUniverseTiltLadderQcProjectionError):
        subject.build_tilt_ladder_projection(package, percent)
    monkeypatch.undo()

    monkeypatch.setattr(subject, "PINNED_PROJECTIONS", {**subject.PINNED_PROJECTIONS, percent: "0" * 64})
    with pytest.raises(subject.SixUniverseTiltLadderQcProjectionError):
        subject.build_tilt_ladder_projection(package, percent)


def test_only_three_named_fractions_are_eligible():
    for invalid in (0, 40, 80, 100, 70.0, True, "70"):
        with pytest.raises(subject.SixUniverseTiltLadderQcProjectionError):
            subject.require_tilt_ladder_profile(invalid)
