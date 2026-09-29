"""Offline generated-source and behavior checks for R278's entry-only arm."""

import ast
from decimal import Decimal

import pytest

from research.analyst_revisions_v2_qc import (
    accepted_risk_six_universe_order_relaxed_qc_projection as loader,
)
from research.analyst_revisions_v2_qc import eight_universe_ar_entry_only_projection as subject
from research.analyst_revisions_v2_qc import eight_universe_ar_on_split_rounding as parent
from research.analyst_revisions_v2_qc import eight_universe_qcom_admitted_projection as eight
from scripts import run_arv2_eight_universe as script
from tests.analyst_revisions_v2.test_qc_relaxed_selection_source import _rows, _snapshots


EXPECTED_PROJECTION_SHA256 = (
    "a9d3c606ade43291277e6ef3bcf9faaf4778bbea6fa1f70c1bc13abf6396a32f"
)
EXPECTED_PROFILE_SHA256 = (
    "27c45839301fe8084a2428c0989d0aa30659dd7b896c13e56d05d94092b935e8"
)


def _sources(projection):
    return {item.project_path: item.source_bytes.decode("ascii")
            for item in projection.source_files}


@pytest.fixture(scope="module")
def family():
    package = script.package()
    return (parent.build_projection(package, "R270"),
            subject.build_projection(package))


def test_exact_corrected_r270_parent_and_four_file_entry_only_edit(family):
    (old, old_profile), (new, profile) = family
    assert old.projection_sha256 == subject.PREDECESSOR_PROJECTION_SHA256
    assert old.profile_sha256 == subject.PREDECESSOR_PROFILE_SHA256
    assert new.projection_sha256 == EXPECTED_PROJECTION_SHA256
    assert new.profile_sha256 == profile["profile_sha256"] == EXPECTED_PROFILE_SHA256
    assert new.package_sha256 == old.package_sha256
    assert new.activation_manifest_sha256 == old.activation_manifest_sha256
    assert new.profile_id == profile["profile_id"]
    assert profile["comparison_arm"] == subject.ARM
    assert profile["analyst_revision_economic_usage"] == subject.ECONOMIC_USAGE
    assert profile["maximum_stock_weight_change_fraction"] == "0.00"
    assert profile["matched_baseline_profile_sha256"] == old_profile[
        "matched_baseline_profile_sha256"]
    assert profile["overnight_holding_drift_rule"] == old_profile[
        "overnight_holding_drift_rule"]
    for key in ("target_gross_exposure", "modeled_fee_bps_per_side",
                "slippage_bps", "admission_leverage", "decision_count",
                "evaluation_start_session", "evaluation_end_session",
                "gate_profile_sha256", "evaluation_profile_sha256"):
        assert profile[key] == old_profile[key]
    before, after = _sources(old), _sources(new)
    assert set(before) == set(after) and len(after) == 17
    assert {path for path in before if before[path] != after[path]} == subject._CHANGED_FILES
    assert before[eight._GATE] == after[eight._GATE]
    assert before[eight._TARGETS] == after[eight._TARGETS]
    assert before[subject.parent.split._BRIDGE] == after[subject.parent.split._BRIDGE]
    assert before[eight._RUNTIME] == after[eight._RUNTIME]
    assert before[eight._DIAGNOSTICS] != after[eight._DIAGNOSTICS]


def test_generated_entry_gate_is_still_r270_but_transfer_is_exact_zero(family):
    (old, _), (new, _) = family
    observations = []
    for source in (old, new):
        with loader._cloud_loader(_sources(source)) as (load, _):
            gate = load(eight._GATE[:-3])
            tilt = load(subject._TARGET[:-3])
            assert gate.MINIMUM_POSITIVE_SCORE_COUNT == 1
            assert gate.UNIVERSE_IDS == eight.UNIVERSES
            per_score = []
            for positive_count in (0, 1, 3):
                snapshots = _snapshots(gate, {"QQQ": _rows(
                    gate, "QQQ", positives=positive_count)})
                construction = gate.build_six_universe_construction(
                    snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
                qqq = next(item for item in construction.sleeves
                           if item.universe_id == "QQQ")
                per_score.append((qqq.positive_score_count,
                                  qqq.matched_security_ids,
                                  qqq.matched_etf_fallback_weight))
                if source is new:
                    assert tilt.MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION == Decimal("0.00")
                    assert tilt.tilt_matched_weights(
                        construction, snapshots) == construction.matched_weights
            observations.append(per_score)
    assert observations[0] == observations[1]
    # If the AR entry gate were removed, zero-positive QQQ would hold cap-ranked
    # stocks instead of its own ETF; the one-score boundary is also binding.
    assert observations[1][0][1] == ()
    assert len(observations[1][1][1]) == 1
    assert len(observations[1][2][1]) == 3


def test_generated_parent_really_transfers_where_entry_only_does_not(family):
    (old, _), (new, _) = family
    outcome = []
    for source in (old, new):
        with loader._cloud_loader(_sources(source)) as (load, _):
            gate = load(eight._GATE[:-3])
            tilt = load(subject._TARGET[:-3])
            snapshots = _snapshots(gate)
            construction = gate.build_six_universe_construction(
                snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
            outcome.append((tuple(item.to_record()
                                  for item in construction.matched_weights),
                            tuple(item.to_record() for item in
                                  tilt.tilt_matched_weights(construction, snapshots))))
    assert outcome[0][0] == outcome[1][0]
    assert outcome[0][1] != outcome[0][0]
    assert outcome[1][1] == outcome[1][0]


def test_new_diagnostic_arm_and_main_class_are_versioned(family):
    (old, _), (new, _) = family
    before, after = _sources(old), _sources(new)
    main = ast.parse(after["main.py"])
    names = [node.name for node in main.body if isinstance(node, ast.ClassDef)]
    assert subject._NEW_CLASS in names and subject._PARENT_CLASS not in names
    diagnostic_calls = [node for node in ast.walk(main)
                        if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name)
                        and node.func.id == "install_matched_diagnostics"]
    assert len(diagnostic_calls) == 1
    assert diagnostic_calls[0].args[1].value == subject.ARM
    assert before[eight._GATE] == after[eight._GATE]
    with loader._cloud_loader(after) as (load, _):
        runtime = load(subject._RUNTIME[:-3])
        assert runtime.require_tilt_profile()["comparison_arm"] == subject.ARM
        assert set(runtime.expected_tilt_custom_statistic_names()) == set(
            eight.STATISTIC_NAMES)


def test_changed_parent_or_non_arm_source_refuses_before_any_qc(family, monkeypatch):
    package = script.package()
    monkeypatch.setattr(subject, "PREDECESSOR_PROJECTION_SHA256", "f" * 64)
    with pytest.raises(subject.EightUniverseEntryOnlyProjectionError,
                       match="predecessor"):
        subject.build_projection(package)
    monkeypatch.setattr(subject, "PREDECESSOR_PROJECTION_SHA256",
                        parent.frozen_manifest()["candidates"][1]["projection_sha256"])
    old_render = subject._render

    def mutated(path, source):
        text = old_render(path, source)
        if path == eight._GATE:
            return text.replace("MINIMUM_POSITIVE_SCORE_COUNT = 1",
                                "MINIMUM_POSITIVE_SCORE_COUNT = 0")
        return text

    monkeypatch.setattr(subject, "_render", mutated)
    with pytest.raises(subject.EightUniverseEntryOnlyProjectionError,
                       match="non-arm"):
        subject.build_projection(package)
