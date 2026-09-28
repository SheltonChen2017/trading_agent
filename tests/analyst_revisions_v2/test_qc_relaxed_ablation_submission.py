"""Isolate the prospective ablation family without cloud or provider access."""

import dataclasses
import hashlib

import pytest

from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as sut
from tests.analyst_revisions_v2 import test_qc_relaxed_submission as legacy


@pytest.fixture
def ablation(tmp_path, monkeypatch):
    projection = legacy.Projection()
    projection.role = "weight-ablation-test"
    rows = []
    for candidate_id, fraction in (("R220", "0.00"), ("R221", "1.00")):
        rows.append({"candidate_id": candidate_id, "kind": "order",
            "project_name": "ARV2 TEST " + candidate_id,
            "backtest_name": "ARV2 TEST " + candidate_id,
            "projection_schema": projection.schema,
            "projection_sha256": projection.projection_sha256,
            "profile_id": projection.profile_id,
            "profile_sha256": projection.profile_sha256,
            "role": projection.role, "tilt_fraction": fraction,
            "source_file_count": 1,
            "total_source_bytes": projection.total_source_byte_count,
            "source_files_sha256": sut._sha(projection.semantic()["source_files"]),
            "statistic_names": ["ARV2_SIX_GATE_ORDER_META", "ARV2_SIX_GATE_ORDER_AGGREGATES"],
            "meta_schema": "test-ablation-meta", "summary_schema": "test-ablation-summary",
            "matched_baseline_profile_sha256": "e" * 64})
    manifest = {"schema": "test-ablation-family", "candidates": rows,
        "package_sha256": projection.package_sha256,
        "activation_manifest_sha256": projection.activation_manifest_sha256,
        "input_control_directory": str(tmp_path)}
    path = tmp_path / "ablation.json"
    path.write_bytes(legacy.canonical(manifest))
    monkeypatch.setattr(sut, "ABLATION_MANIFEST_PATH", path)
    monkeypatch.setattr(sut, "FROZEN_ABLATION_MANIFEST_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(sut, "_require_inputs", lambda plan: None)
    monkeypatch.setattr(sut.common, "_client", lambda api: None)
    fake = legacy.Fake()
    monkeypatch.setattr(sut.common, "_post", fake.post)
    plan = sut.build_plan("R220", legacy.ORG, tmp_path / "control", family="weight_ablation")
    return plan, projection, fake, manifest


def test_ablation_preview_uses_separate_pin_not_historical_pin(ablation):
    plan, projection, _, _ = ablation
    identity = sut.preview(plan, projection)
    assert identity["manifest_sha256"] == sut.FROZEN_ABLATION_MANIFEST_SHA256
    assert identity["manifest_sha256"] != sut.FROZEN_MANIFEST_SHA256
    assert identity["candidate_id"] == "R220"
    assert sut._candidate(dataclasses.replace(plan, candidate_id="R221"))["tilt_fraction"] == "1.00"


@pytest.mark.parametrize("candidate_id,family", [
    ("R220", "relaxed"), ("R214", "weight_ablation"),
    ("R209", "weight_ablation"), ("R220", "unknown"), ("R220", True)])
def test_wrong_family_refused_before_external_io(ablation, candidate_id, family):
    plan, projection, fake, _ = ablation
    with pytest.raises(sut.RelaxedQcSubmissionError):
        sut.launch(dataclasses.replace(plan, candidate_id=candidate_id, family=family), projection, fake)
    assert fake.calls == []


def test_historical_manifest_and_default_plan_unchanged(ablation, monkeypatch):
    plan, _, _, _ = ablation
    historical = sut._manifest()
    assert [row["candidate_id"] for row in historical["candidates"]] == ["R" + str(n) for n in range(209, 220)]
    assert hashlib.sha256(sut.MANIFEST_PATH.read_bytes()).hexdigest() == sut.FROZEN_MANIFEST_SHA256
    default_plan = sut.build_plan("R214", legacy.ORG, plan.control_directory)
    assert default_plan.family == "relaxed"
    assert sut._plan_manifest(default_plan) == historical
    sentinel = {"legacy": "parser fixture"}
    monkeypatch.setattr(sut, "_manifest", lambda: sentinel)
    assert sut._plan_manifest(object()) is sentinel


@pytest.mark.parametrize("mutation", ["ids", "fractions", "kind", "extra"])
def test_authenticated_ablation_manifest_still_requires_exact_census(ablation, monkeypatch, mutation):
    plan, _, _, manifest = ablation
    if mutation == "ids":
        manifest["candidates"][0]["candidate_id"] = "R222"
    elif mutation == "fractions":
        manifest["candidates"][0]["tilt_fraction"] = "0.20"
    elif mutation == "kind":
        manifest["candidates"][0]["kind"] = "coverage"
    else:
        manifest["candidates"].append(dict(manifest["candidates"][0]))
    sut.ABLATION_MANIFEST_PATH.write_bytes(legacy.canonical(manifest))
    monkeypatch.setattr(sut, "FROZEN_ABLATION_MANIFEST_SHA256", hashlib.sha256(sut.ABLATION_MANIFEST_PATH.read_bytes()).hexdigest())
    with pytest.raises(sut.RelaxedQcSubmissionError, match="census"):
        sut._candidate(plan)


def test_ablation_unpinned_or_changed_manifest_refused(ablation, monkeypatch):
    plan, projection, fake, _ = ablation
    monkeypatch.setattr(sut, "FROZEN_ABLATION_MANIFEST_SHA256", None)
    with pytest.raises(sut.RelaxedQcSubmissionError, match="frozen manifest"):
        sut.launch(plan, projection, fake)
    assert fake.calls == []


def test_ablation_three_compile_failures_consume_same_project_slots(ablation):
    plan, projection, fake, _ = ablation
    fake.compile_state = "BuildError"
    for attempt in (1, 2, 3):
        slot = dataclasses.replace(plan, attempt=attempt)
        with pytest.raises(sut.RelaxedQcSubmissionError, match="compile failed"):
            sut.launch(slot, projection, fake)
        assert sut._path(slot, "claim").exists()
        assert sut.common._read(sut._path(slot, "terminal"))["status"] == "BuildError"
    before = len(fake.calls)
    with pytest.raises(sut.RelaxedQcSubmissionError, match="bound"):
        sut.launch(dataclasses.replace(plan, attempt=4), projection, fake)
    assert len(fake.calls) == before
    assert sum(endpoint == "projects/create" for endpoint, _ in fake.calls) == 1


def test_ablation_receipt_rejects_historical_manifest_pin(ablation):
    plan, projection, fake, _ = ablation
    launch = sut.launch(plan, projection, fake)
    assert sut._receipt(plan, launch)["manifest_sha256"] == sut.FROZEN_ABLATION_MANIFEST_SHA256
    identity = sut.common._read(sut._path(plan, "claim"))
    identity["manifest_sha256"] = sut.FROZEN_MANIFEST_SHA256
    sut._path(plan, "claim").write_bytes(legacy.canonical(identity))
    launch["manifest_sha256"] = sut.FROZEN_MANIFEST_SHA256
    sut._path(plan, "launch").write_bytes(legacy.canonical(launch))
    with pytest.raises(sut.RelaxedQcSubmissionError, match="claim"):
        sut._receipt(plan, launch)


def test_ablation_launch_and_read_claim_remain_one_use(ablation, monkeypatch):
    plan, projection, fake, _ = ablation
    launch = sut.launch(plan, projection, fake)
    with pytest.raises(sut.RelaxedQcSubmissionError, match="consumed"):
        sut.launch(plan, projection, fake)
    fake.status = "Completed."
    sut.poll_status(plan, launch, fake)
    fake.statistics = {name: "{}" for name in sut._candidate(plan)["statistic_names"]}
    monkeypatch.setattr(sut, "_parse_order", lambda plan, statistics: {"run_valid": True})
    assert sut.read_result_once(plan, launch, fake)["run_valid"] is True
    assert sut._read_artifact(sut._path(plan, "result"))["manifest_sha256"] == sut.FROZEN_ABLATION_MANIFEST_SHA256
    with pytest.raises(sut.common.SixUniverseSettlementSubmissionError):
        sut.read_result_once(plan, launch, fake)
    assert sum(endpoint == "backtests/read" for endpoint, _ in fake.calls) == 1


def test_ablation_cannot_inherit_r209_transport_recovery(ablation):
    plan, projection, fake, _ = ablation
    launch = sut.launch(plan, projection, fake)
    fake.status = "Completed."
    sut.poll_status(plan, launch, fake)
    with pytest.raises(sut.RelaxedQcSubmissionError, match="recovery"):
        sut.read_result_once(plan, launch, fake, recover_r209_transport=True)
    assert not any(endpoint == "backtests/read" for endpoint, _ in fake.calls)


def test_ablation_input_receipt_uses_its_own_manifest(ablation, monkeypatch):
    plan, _, _, manifest = ablation
    # Exercise the real helper, not this fixture's no-I/O replacement.
    seen = []
    monkeypatch.setattr(sut.recent, "build_plan", lambda candidate, org, control:
        type("InputPlan", (), {"package_sha256": manifest["package_sha256"],
            "activation_manifest_sha256": manifest["activation_manifest_sha256"]})())
    monkeypatch.setattr(sut.recent, "require_uploaded_inputs", lambda prior: seen.append(prior))
    monkeypatch.setattr(sut, "_manifest", lambda: pytest.fail("legacy manifest used"))
    # Function was captured by the module fixture before monkeypatching below.
    REAL_REQUIRE_INPUTS(plan)
    assert len(seen) == 1


@pytest.mark.parametrize("candidate_id", ["R220", "R221"])
def test_real_order_parser_authenticates_each_ablation_fraction(ablation, candidate_id):
    plan, _, _, _ = ablation
    plan = dataclasses.replace(plan, candidate_id=candidate_id)
    row = sut._candidate(plan)
    aggregate, _, meta = legacy.order_fixture()
    aggregate.update(schema=row["summary_schema"], role=row["role"],
        profile_id=row["profile_id"], profile_sha256=row["profile_sha256"],
        maximum_stock_weight_change_fraction=row["tilt_fraction"],
        matched_baseline_profile_sha256=row["matched_baseline_profile_sha256"])
    raw = legacy.canonical(aggregate).decode("ascii")
    meta.update(schema=row["meta_schema"], role=row["role"],
        profile_id=row["profile_id"], profile_sha256=row["profile_sha256"],
        aggregate_schema=row["summary_schema"],
        aggregate_sha256=hashlib.sha256(raw.encode("ascii")).hexdigest())
    stats = {"ARV2_SIX_GATE_ORDER_META": legacy.canonical(meta).decode("ascii"),
             "ARV2_SIX_GATE_ORDER_AGGREGATES": raw}
    assert sut._parse_order(plan, stats)["run_valid"] is True
    aggregate["maximum_stock_weight_change_fraction"] = "0.20"
    raw = legacy.canonical(aggregate).decode("ascii")
    meta["aggregate_sha256"] = hashlib.sha256(raw.encode("ascii")).hexdigest()
    stats.update(ARV2_SIX_GATE_ORDER_META=legacy.canonical(meta).decode("ascii"),
                 ARV2_SIX_GATE_ORDER_AGGREGATES=raw)
    with pytest.raises(sut.RelaxedQcSubmissionError, match="aggregate identity"):
        sut._parse_order(plan, stats)


REAL_REQUIRE_INPUTS = sut._require_inputs
