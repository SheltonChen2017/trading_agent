"""Offline seven-arm split correction and immutable manifest guards."""

import ast
import copy
import hashlib

import pytest

from research.analyst_revisions_v2_qc import eight_universe_ar_on_split_rounding as subject
from research.analyst_revisions_v2_qc import eight_universe_r268_a3_split_rounding as baseline_a3
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from scripts.run_arv2_qcom_restored import package


_CHANGED_SOURCE_FILES = {
    "accepted_risk_six_universe_order_qc_runtime.py",
    "accepted_risk_six_universe_order_bridge_qc_runtime.py",
    "accepted_risk_six_universe_order_tilt_qc_runtime.py",
}


@pytest.fixture(scope="module")
def built():
    inputs = package()
    original = {}
    corrected = {}
    current = None
    real_overlay = subject.split.correct_projection

    def capture(projection, profile, **kwargs):
        original[current] = (projection, profile)
        return real_overlay(projection, profile, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subject.split, "correct_projection", capture)
        for candidate in subject.CANDIDATES:
            current = candidate
            corrected[candidate] = subject.build_projection(inputs, candidate)
    assert set(original) == set(corrected) == set(subject.CANDIDATES)
    return {"inputs": inputs, "original": original, "corrected": corrected}


def _source(projection, name):
    return next(item.source_bytes.decode("ascii")
                for item in projection.source_files if item.project_path == name)


def _split_method(projection):
    tree = ast.parse(_source(projection,
        "accepted_risk_six_universe_order_qc_runtime.py"))
    drivers = [node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == "AcceptedRiskSixUniverseOrderQcDriver"]
    methods = [node for driver in drivers for node in driver.body
               if isinstance(node, ast.FunctionDef)
               and node.name == "_holding_drift_replan"]
    assert len(methods) == 1
    return ast.dump(methods[0], include_attributes=False)


def test_corrected_manifest_rebuilds_exactly_from_seven_original_rows(built, monkeypatch):
    old = adapter._eight_universe_manifest()
    before = subject.MANIFEST_PATH.read_bytes()
    assert hashlib.sha256(before).hexdigest() == subject.FROZEN_MANIFEST_SHA256
    monkeypatch.setattr(subject, "build_projection",
                        lambda _inputs, candidate: built["corrected"][candidate])
    rebuilt = subject.freeze_manifest(object())
    assert rebuilt == subject.frozen_manifest()
    assert tuple(row["candidate_id"] for row in rebuilt["candidates"]) == subject.CANDIDATES
    assert rebuilt["original_manifest_sha256"] == adapter.FROZEN_EIGHT_UNIVERSE_MANIFEST_SHA256
    assert rebuilt["original_candidate_sha256s"] == {
        candidate: adapter._sha(subject._original_rows()[candidate])
        for candidate in subject.CANDIDATES}
    assert rebuilt["baseline_a3_manifest_sha256"] == adapter.FROZEN_EIGHT_R268_A3_MANIFEST_SHA256
    assert hashlib.sha256(subject.MANIFEST_PATH.read_bytes()).hexdigest() == subject.FROZEN_MANIFEST_SHA256
    assert adapter._eight_universe_manifest() == old


def test_all_seven_sources_use_a3_split_rule_and_change_only_three_files(built):
    a3, a3_profile = baseline_a3.build_projection(built["inputs"])
    a3_method = _split_method(a3)
    rows = {row["candidate_id"]: row for row in subject.frozen_manifest()["candidates"]}
    for candidate, (corrected, profile) in built["corrected"].items():
        old, old_profile = built["original"][candidate]
        old_files = {item.project_path: item.content_sha256 for item in old.source_files}
        new_files = {item.project_path: item.content_sha256 for item in corrected.source_files}
        assert {path for path in old_files if old_files[path] != new_files[path]} == _CHANGED_SOURCE_FILES
        assert _split_method(corrected) == a3_method
        assert profile["overnight_holding_drift_rule"] == a3_profile["overnight_holding_drift_rule"]
        assert profile["matched_baseline_profile_sha256"] != a3_profile[
            "matched_baseline_profile_sha256"]
        assert profile["matched_baseline_profile_sha256"] != old_profile[
            "matched_baseline_profile_sha256"]
        assert all(profile[key] == old_profile[key] for key in old_profile
                   if key not in {"schema", "profile_id", "profile_sha256",
                                  "overnight_holding_drift_rule",
                                  "cap90_predecessor_profile_sha256",
                                  "matched_baseline_profile_sha256"})
        assert rows[candidate]["projection_sha256"] == corrected.projection_sha256
        assert rows[candidate]["profile_sha256"] == profile["profile_sha256"]
        assert rows[candidate]["source_file_count"] == 17
        for key in ("source_candidate_id", "source_family", "source_manifest_sha256",
                    "source_projection_sha256", "source_profile_sha256"):
            assert rows[candidate][key] == subject._original_rows()[candidate][key]


@pytest.mark.parametrize("defect", ["reorder", "old_pin", "old_candidate",
    "a3_pin", "split_rule", "package", "activation", "tilt", "project",
    "source_parent", "parent_profile", "old_bridge", "profile", "source",
    "statistics", "extra_row"])
def test_manifest_refuses_altered_lineage_or_economics(defect):
    changed = copy.deepcopy(subject.frozen_manifest())
    row = changed["candidates"][0]
    old = subject._original_rows()["R269"]
    if defect == "reorder":
        changed["candidates"][0], changed["candidates"][1] = (
            changed["candidates"][1], changed["candidates"][0])
    elif defect == "old_pin":
        changed["original_manifest_sha256"] = "0" * 64
    elif defect == "old_candidate":
        changed["original_candidate_sha256s"]["R269"] = "0" * 64
    elif defect == "a3_pin":
        changed["baseline_a3_manifest_sha256"] = "0" * 64
    elif defect == "split_rule":
        changed["split_rule"] = "unconditional_split_replan"
    elif defect == "package":
        changed["package_sha256"] = "0" * 64
    elif defect == "activation":
        changed["activation_manifest_sha256"] = "0" * 64
    elif defect == "tilt":
        row["tilt_fraction"] = "1.00"
    elif defect == "project":
        row["project_name"] += " changed"
    elif defect == "source_parent":
        row["source_projection_sha256"] = "0" * 64
    elif defect == "parent_profile":
        row["source_profile_sha256"] = "0" * 64
    elif defect == "old_bridge":
        row["matched_baseline_profile_sha256"] = old[
            "matched_baseline_profile_sha256"]
    elif defect == "profile":
        row["profile_sha256"] = old["profile_sha256"]
    elif defect == "source":
        row["source_files_sha256"] = old["source_files_sha256"]
    elif defect == "statistics":
        row["statistic_names"] = []
    else:
        changed["candidates"].append(copy.deepcopy(row))
    with pytest.raises(adapter.RelaxedQcSubmissionError):
        subject.validate_manifest(changed)


def test_non_ladder_candidate_refused_before_package_access():
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="not frozen"):
        subject.build_projection(None, "R268")
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="not frozen"):
        subject.build_projection(None, "R276")
