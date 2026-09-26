"""Executable projected-module identities and recent period boundary proofs."""

import ast
import builtins
from datetime import date, datetime
from decimal import Decimal, localcontext
import hashlib
from pathlib import Path
import sys
import types

import pytest

from data.exchange_calendar import trading_sessions
from research.analyst_revisions_v2_qc import accepted_risk_delta_order_package as delta
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_tilt_recent_qc_projection as subject
from tests.analyst_revisions_v2 import test_qc_six_universe_tilt_ladder_floor_projection as old_tests
from tests.analyst_revisions_v2 import test_qc_accepted_risk_six_universe_gate as gate_fixtures


@pytest.fixture(scope="module")
def prior_package():
    if not old_tests.PACKAGE_PATH.is_dir():
        pytest.skip("local ignored exact delta package unavailable")
    return delta.load_accepted_risk_delta_order_package(
        old_tests.PACKAGE_PATH,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256)


@pytest.fixture(scope="module")
def sources(prior_package):
    # Synthetic activation only renders code for offline behavioural checks.
    # It is never a package or public launchable projection authority.
    activation = types.SimpleNamespace(
        object_store_key="arv2/offline-fixture/transport-manifest.json",
        content_sha256="f" * 64, byte_count=4016)
    result = {}
    for percent in subject.CANDIDATE_IDS:
        predecessor = subject._prior.build_tilt_floor_projection(prior_package, percent)
        result[percent] = {item.project_path: subject._candidate_source(
            item.project_path, item.source_bytes.decode("ascii"), percent,
            predecessor, activation) for item in predecessor.source_files}
    return result


def _cloud_modules(sources, monkeypatch):
    names = {path[:-3] for path in sources if path != "main.py"}
    modules = {name: types.ModuleType(name) for name in names}
    def cloud_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "research" or name.startswith("research."):
            raise AssertionError("projected cloud closure fell back to host code")
        return builtins.__import__(name, globals, locals, fromlist, level)
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
        module.__dict__["__builtins__"] = {
            **vars(builtins), "__import__": cloud_import}
    completed = set()
    visiting = set()

    def load(name):
        if name in completed:
            return
        assert name not in visiting, "projected source imports are cyclic"
        visiting.add(name)
        source = sources[name + ".py"]
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in names:
                        load(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module in names:
                load(node.module)
        exec(compile(source, name + ".py", "exec"), modules[name].__dict__)
        visiting.remove(name)
        completed.add(name)

    for name in sorted(names):
        load(name)
    return modules


def test_generated_profiles_agree_at_every_layer(sources, monkeypatch):
    for percent, files in sources.items():
        modules = _cloud_modules(files, monkeypatch)
        evaluation = modules["accepted_risk_six_universe_gate_evaluator"]
        base = modules["accepted_risk_six_universe_order_qc_runtime"]
        bridge = modules["accepted_risk_six_universe_order_bridge_qc_runtime"]
        tilt = modules["accepted_risk_six_universe_order_tilt_qc_runtime"]
        assert evaluation.TOP10_CAP90_EXPLORATORY_PROFILE.to_record() == subject._evaluation_profile()
        matched = bridge.require_bridge_profile("matched")
        assert matched == subject._matched_profile()
        assert matched["profile_sha256"] == subject.MATCHED_BASELINE_PROFILE_SHA256
        assert matched["cap90_predecessor_profile_sha256"] == (
            base.require_six_universe_order_profile("matched", variant=base.CAP90_VARIANT)["profile_sha256"])
        assert tilt.require_tilt_profile() == subject.require_tilt_recent_profile(percent)
        assert base.EVALUATION_START_SESSION == "2025-08-01"
        assert base.EVALUATION_END_SESSION == "2026-09-25"
        assert (base.EXPECTED_SESSION_COUNT, base.EXPECTED_DECISION_COUNT) == (290, 61)


def test_missing_cloud_dependency_cannot_be_masked_by_host_fallback(sources, monkeypatch):
    broken = dict(sources[100])
    broken.pop("accepted_risk_order_level_core.py")
    monkeypatch.delitem(sys.modules, "accepted_risk_order_level_core", raising=False)
    with pytest.raises(AssertionError, match="fell back to host"):
        _cloud_modules(broken, monkeypatch)


def test_actual_calendar_and_generated_decision_schedule(sources, monkeypatch):
    modules = _cloud_modules(sources[100], monkeypatch)
    evaluation = modules["accepted_risk_six_universe_gate_evaluator"]
    ratings = modules["accepted_risk_preliminary_rating_evaluator"]
    axis = tuple(item.isoformat() for item in trading_sessions(
        date(2025, 7, 24), date(2026, 9, 25)))
    period = tuple(session for session in axis if session >= "2025-08-01")
    assert len(period) == 290 and len(period) - 1 == 289
    value = ratings.PreliminaryRatingInput(
        "fixture", "a" * 64, "arv2-benchmark-SPY", axis, (), (), (), 1, 1, 1)
    decisions = evaluation.decision_sessions_for_input(value)
    assert len(decisions) == 61
    assert decisions[0] == "2025-08-01" and decisions[-1] == "2026-09-21"
    assert axis[axis.index(decisions[0]) + 1] == "2025-08-04"
    assert len(axis[:axis.index("2025-08-01")]) >= 5
    # Stale full-window schedule cannot be silently accepted in this source.
    evaluation.EXPECTED_DECISION_SESSION_COUNT = 261
    with pytest.raises(evaluation.SixUniverseGateEvaluationError, match="decision geometry"):
        evaluation.decision_sessions_for_input(value)


def test_generated_tilt_keeps_original_economics_and_safe_donor_floors(sources, monkeypatch):
    for snapshots in (gate_fixtures._snapshots(), old_tests._shared_worst_donor_snapshots()):
        for percent, files in sources.items():
            modules = _cloud_modules(files, monkeypatch)
            gate = modules["accepted_risk_six_universe_gate"]
            # Rehydrate the fixture into the projected module's exact classes.
            cloud_snapshots = tuple(gate.UniverseSnapshot(
                universe_id=row.universe_id, etf_ticker=row.etf_ticker,
                etf_security_id=row.etf_security_id,
                constituents=tuple(gate.UniverseConstituent(**{
                    field: getattr(item, field) for field in item.__dataclass_fields__})
                    for item in row.constituents)) for row in snapshots)
            construction = gate.build_six_universe_construction(
                cloud_snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
            targets = modules["accepted_risk_six_universe_order_tilt_targets"]
            tilted, sleeves = old_tests._tilt_and_capture_sleeves(
                targets, files[old_tests.TARGETS_PATH], construction, cloud_snapshots)
            assert targets.MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION == Decimal(percent) / 100
            assert all(item.weight > 0 for item in tilted)
            assert all(item.weight <= Decimal("0.05") for item in tilted if item.asset_kind == "stock")
            with localcontext() as context:
                context.prec = 96
                assert sum((item.weight for item in tilted), Decimal(0)) == Decimal("0.98")
                for _, before, after in sleeves:
                    assert all(item >= Decimal("1e-30") for item in after.values())
                    assert sum(before.values(), Decimal(0)) == sum(after.values(), Decimal(0))


def test_bridge_terminal_clock_is_exact_next_midnight(sources, monkeypatch):
    modules = _cloud_modules(sources[100], monkeypatch)
    bridge = modules["accepted_risk_six_universe_order_bridge_qc_runtime"]
    class ReachedAggregate(Exception):
        pass
    def aggregate():
        raise ReachedAggregate
    context = types.SimpleNamespace(
        _require_initialized=lambda: None, _aggregate=aggregate,
        _algorithm=types.SimpleNamespace(live_mode=False, time=datetime(2026, 9, 26)))
    with pytest.raises(ReachedAggregate):
        bridge.BridgeAdmissionMixin.on_end_of_algorithm(context)
    for stamp in (datetime(2026, 1, 1), datetime(2026, 9, 25, 23, 59, 59),
                  datetime(2026, 9, 26, 0, 0, 1)):
        context._algorithm.time = stamp
        with pytest.raises(bridge.AcceptedRiskSixUniverseOrderBridgeQcRuntimeError,
                           match="next midnight"):
            bridge.BridgeAdmissionMixin.on_end_of_algorithm(context)


@pytest.mark.parametrize("percent", (True, 80, 220, 250, 300, "100", None))
def test_only_six_exact_recent_capacities_are_admitted(percent):
    with pytest.raises(subject.SixUniverseTiltRecentQcProjectionError, match="pinned"):
        subject.require_tilt_recent_profile(percent)


def test_exact_source_replace_refuses_missing_points():
    with pytest.raises(subject.SixUniverseTiltRecentQcProjectionError,
                       match="replacement point"):
        subject._period_source("accepted_risk_six_universe_gate_evaluator.py", "x = 1")


def test_profile_and_matched_baseline_pin_drift_refuse(monkeypatch):
    monkeypatch.setitem(subject.PINNED_PROFILE_SHA256S, 100, "0" * 64)
    with pytest.raises(subject.SixUniverseTiltRecentQcProjectionError,
                       match="profile changed from exact pin"):
        subject.require_tilt_recent_profile(100)
    monkeypatch.setattr(subject, "MATCHED_BASELINE_PROFILE_SHA256", "0" * 64)
    with pytest.raises(subject.SixUniverseTiltRecentQcProjectionError,
                       match="matched profile changed"):
        subject.require_tilt_recent_profile(120)


def test_old_package_cannot_stand_in_for_latest_inputs(prior_package):
    with pytest.raises(subject.SixUniverseTiltRecentQcProjectionError,
                       match="recent package or activation"):
        subject.build_short_window_tilt_projection(
            prior_package, prior_package.package, 100)


def test_main_dates_and_normalization_keep_exact_executable_ast(
    prior_package, sources, monkeypatch,
):
    activation = types.SimpleNamespace(
        object_store_key="arv2/offline-fixture/transport-manifest.json",
        content_sha256="f" * 64, byte_count=4016)
    prior = subject._prior.build_tilt_floor_projection(prior_package, 100)
    original = next(item.source_bytes.decode("ascii") for item in prior.source_files
                    if item.project_path == "main.py")
    rendered = sources[100]["main.py"]
    assert "self.set_start_date(2025, 7, 24)" in rendered
    assert "self.set_end_date(2026, 9, 25)" in rendered
    assert len(rendered.encode("ascii")) < len(original.encode("ascii"))
    for source in sources[100].values():
        compile("from AlgorithmImports import *\n" + source, "projection", "exec")
    monkeypatch.setattr(subject.ast, "unparse", lambda _tree: "x = 1")
    with pytest.raises(subject.SixUniverseTiltRecentQcProjectionError,
                       match="executable AST"):
        subject._candidate_source("main.py", original, 100, prior, activation)


def test_distinct_manifests_may_share_the_same_byte_count(prior_package):
    prior = subject._prior.build_tilt_floor_projection(prior_package, 100)
    original = next(item.source_bytes.decode("ascii") for item in prior.source_files
                    if item.project_path == "main.py")
    activation = types.SimpleNamespace(
        object_store_key="arv2/distinct-fixture/transport-manifest.json",
        content_sha256="f" * 64, byte_count=prior.activation_manifest_byte_count)
    rendered = subject._candidate_source("main.py", original, 100, prior, activation)
    assert activation.object_store_key in rendered and activation.content_sha256 in rendered
    assert f"activation_manifest_byte_count={activation.byte_count}" in rendered
    with pytest.raises(subject.SixUniverseTiltRecentQcProjectionError,
                       match="replacement point"):
        subject._candidate_source("main.py", original.replace(
            f"activation_manifest_byte_count={activation.byte_count}", "wrong_slot=1"),
            100, prior, activation)
