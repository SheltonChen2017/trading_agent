"""Authenticate real production pins and reject unmatched comparison fixtures."""

import copy
import hashlib
import json

import pytest

from scripts import run_arv2_weight_ablation as script
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from tests.analyst_revisions_v2 import test_qc_recent_coverage_projection as inputs
from tests.analyst_revisions_v2 import test_qc_relaxed_submission as legacy

prior_package = inputs.prior_package
actual_package = inputs.actual_package


def test_actual_production_ablation_freeze_and_successful_predecessor_are_exact(prior_package, actual_package, monkeypatch, tmp_path):
    monkeypatch.setattr(script, "packages", lambda: (prior_package, actual_package))
    assert script.freeze() == adapter._ablation_manifest()
    predecessor = next(row for row in adapter._manifest()["candidates"] if row["candidate_id"] == "R214")
    on = adapter._ablation_manifest()["candidates"][1]
    for key in ("projection_sha256", "profile_sha256", "source_files_sha256", "matched_baseline_profile_sha256"):
        assert on[key] == predecessor[key]
    for candidate in script.PAIR:
        plan = adapter.build_plan(candidate, "a" * 32, tmp_path / "control", family="weight_ablation")
        adapter.preview(plan, script.projected(candidate)[0])


def test_actual_all25_manifest_source_and_exclusive_family_match(prior_package, actual_package, monkeypatch, tmp_path):
    monkeypatch.setattr(script, "packages", lambda: (prior_package, actual_package))
    assert script.freeze(all25=True) == adapter._coverage25_manifest()
    plan = adapter.build_plan("R222", "a" * 32, tmp_path / "control", family="coverage25")
    adapter.preview(plan, script.projected("R222")[0])
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="not frozen"):
        adapter.build_plan("R222", "a" * 32, tmp_path / "control", family="weight_ablation")


@pytest.fixture
def synthetic_cached_pair(tmp_path, monkeypatch):
    """Bounded transport fixtures only; no launch or real outcome authority."""
    family = copy.deepcopy(adapter._ablation_manifest())
    files = [["main.py", "1" * 64, 8]]
    for row in family["candidates"]:
        row["source_files_sha256"] = adapter._sha(files)
    manifest_path = tmp_path / "synthetic-ablation.json"
    manifest_path.write_bytes(adapter.common._canonical(family))
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    monkeypatch.setattr(adapter, "ABLATION_MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(adapter, "FROZEN_ABLATION_MANIFEST_SHA256", manifest_sha)
    monkeypatch.setattr(script, "CONTROL", tmp_path)
    arms = {}
    for index, row in enumerate(family["candidates"]):
        candidate = row["candidate_id"]
        plan = adapter.build_plan(candidate, "a" * 32, tmp_path, family="weight_ablation")
        identity = {"candidate_id": candidate, "attempt": 1,
            "manifest_sha256": manifest_sha, "candidate_sha256": adapter._sha(row),
            "projection_sha256": row["projection_sha256"], "profile_id": row["profile_id"],
            "profile_sha256": row["profile_sha256"], "package_sha256": family["package_sha256"],
            "activation_manifest_sha256": family["activation_manifest_sha256"], "source_files": files}
        launch = {**identity, "project_id": 100 + index,
            "project_name": row["project_name"], "compile_id": "e" * 32,
            "backtest_id": str(index + 1) * 32, "backtest_name": row["backtest_name"] + " A1"}
        expected = {"candidate_id": candidate, "attempt": 1, "project_id": launch["project_id"],
            "backtest_id": launch["backtest_id"], "status": "Completed."}
        for suffix, value in (("claim", identity), ("launch", launch),
                              ("terminal", expected), ("read-claim", expected)):
            adapter.common._write(adapter._path(plan, suffix), value)
        aggregate, _, meta = legacy.order_fixture()
        aggregate.update(schema=row["summary_schema"], role=row["role"],
            profile_id=row["profile_id"], profile_sha256=row["profile_sha256"],
            maximum_stock_weight_change_fraction=row["tilt_fraction"],
            matched_baseline_profile_sha256=row["matched_baseline_profile_sha256"])
        aggregate["account"]["cumulative_return"] = "0.50" if index == 0 else "0.55"
        meta.update(schema=row["meta_schema"], role=row["role"], profile_id=row["profile_id"],
            profile_sha256=row["profile_sha256"], package_sha256=family["package_sha256"],
            activation_manifest_sha256=family["activation_manifest_sha256"],
            aggregate_schema=row["summary_schema"])
        raw = adapter.common._canonical(aggregate).decode("ascii")
        meta["aggregate_sha256"] = hashlib.sha256(raw.encode("ascii")).hexdigest()
        statistics = {"ARV2_SIX_GATE_ORDER_META": adapter.common._canonical(meta).decode("ascii"),
            "ARV2_SIX_GATE_ORDER_AGGREGATES": raw}
        raw_record = {**expected, "statistics": statistics}
        result = {**expected, **adapter._parse_order(plan, statistics),
            "manifest_sha256": manifest_sha, "projection_sha256": row["projection_sha256"]}
        adapter._write_artifact(adapter._path(plan, "raw-custom"), raw_record)
        adapter._write_artifact(adapter._path(plan, "result"), result)
        arms[candidate] = (plan, aggregate, meta, raw_record, result)
    return arms


@pytest.mark.parametrize("defect", (None, "invalid", "path", "sleeves", "geometry", "baseline"))
def test_cached_comparison_requires_two_valid_identical_baselines(synthetic_cached_pair, defect):
    plan, aggregate, meta, raw_record, result = synthetic_cached_pair["R221"]
    if defect == "invalid":
        result["run_valid"] = False
        adapter._path(plan, "result").write_bytes(adapter.common._canonical(result))
    elif defect:
        if defect == "path":
            aggregate["matched_baseline_target_path_sha256"] = "c" * 64
        elif defect == "baseline":
            aggregate["matched_baseline_profile_sha256"] = "c" * 64
        elif defect == "sleeves":
            aggregate["sleeve_diagnostics"]["rows"].append([1])
        else:
            aggregate["account"]["observation_count"] = 289
        raw = adapter.common._canonical(aggregate).decode("ascii")
        meta["aggregate_sha256"] = hashlib.sha256(raw.encode("ascii")).hexdigest()
        raw_record["statistics"].update(ARV2_SIX_GATE_ORDER_META=adapter.common._canonical(meta).decode("ascii"),
            ARV2_SIX_GATE_ORDER_AGGREGATES=raw)
        adapter._path(plan, "raw-custom").write_bytes(adapter.common._canonical(raw_record))
        if defect == "path":
            result.update(adapter._parse_order(plan, raw_record["statistics"]))
            adapter._path(plan, "result").write_bytes(adapter.common._canonical(result))
    if defect:
        with pytest.raises(ValueError):
            script.compare_cached()
    else:
        result = script.compare_cached()
        assert result["net_return_spread_percentage_points"] == "5.00"
        assert result["analyst_entry_and_count_gates_retained"] is True
        assert result["weight_tilt_only"] is True


@pytest.mark.parametrize("defect", ("candidate", "fraction", "copied_arm", "projection", "read_claim", "claim"))
def test_cached_comparison_authenticates_arm_receipt_and_raw_statistics(synthetic_cached_pair, defect):
    plan, aggregate, meta, raw_record, result = synthetic_cached_pair["R221"]
    if defect == "candidate":
        result["candidate_id"] = "R220"
    elif defect == "projection":
        result["projection_sha256"] = "c" * 64
    elif defect == "copied_arm":
        off_plan = synthetic_cached_pair["R220"][0]
        for suffix in ("result", "raw-custom"):
            adapter._path(plan, suffix).write_bytes(adapter._path(off_plan, suffix).read_bytes())
    elif defect == "fraction":
        aggregate["maximum_stock_weight_change_fraction"] = "0.00"
        raw = adapter.common._canonical(aggregate).decode("ascii")
        meta["aggregate_sha256"] = hashlib.sha256(raw.encode("ascii")).hexdigest()
        raw_record["statistics"].update(ARV2_SIX_GATE_ORDER_META=adapter.common._canonical(meta).decode("ascii"),
            ARV2_SIX_GATE_ORDER_AGGREGATES=raw)
        adapter._path(plan, "raw-custom").write_bytes(adapter.common._canonical(raw_record))
    else:
        suffix = "read-claim" if defect == "read_claim" else "claim"
        value = adapter.common._read(adapter._path(plan, suffix))
        value["candidate_id"] = "R220"
        adapter._path(plan, suffix).write_bytes(adapter.common._canonical(value))
    if defect in {"candidate", "projection"}:
        adapter._path(plan, "result").write_bytes(adapter.common._canonical(result))
    with pytest.raises(ValueError):
        script.compare_cached()
