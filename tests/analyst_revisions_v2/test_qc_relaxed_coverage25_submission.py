"""Separate one-candidate all-25% research family, without any external I/O."""

import dataclasses
import hashlib

import pytest

from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as sut
from tests.analyst_revisions_v2 import test_qc_relaxed_submission as legacy
from tests.analyst_revisions_v2.test_qc_relaxed_ablation_submission import ablation


@pytest.fixture
def coverage25(ablation, monkeypatch):
    plan, projection, fake, predecessor = ablation
    manifest = {**predecessor, "schema": "test-coverage25-family",
        "candidates": [{**predecessor["candidates"][1], "candidate_id": "R222",
            "project_name": "ARV2 TEST R222", "backtest_name": "ARV2 TEST R222"}]}
    path = plan.control_directory.parent / "coverage25.json"
    path.write_bytes(legacy.canonical(manifest))
    monkeypatch.setattr(sut, "COVERAGE25_MANIFEST_PATH", path)
    monkeypatch.setattr(sut, "FROZEN_COVERAGE25_MANIFEST_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    plan = sut.build_plan("R222", legacy.ORG, plan.control_directory, family="coverage25")
    return plan, projection, fake, manifest


def test_three_manifest_families_have_disjoint_candidate_censuses(coverage25):
    plan, projection, _, _ = coverage25
    assert [row["candidate_id"] for row in sut._manifest()["candidates"]] == ["R" + str(n) for n in range(209, 220)]
    assert [row["candidate_id"] for row in sut._ablation_manifest()["candidates"]] == ["R220", "R221"]
    assert [row["candidate_id"] for row in sut._coverage25_manifest()["candidates"]] == ["R222"]
    assert len({sut.FROZEN_MANIFEST_SHA256, sut.FROZEN_ABLATION_MANIFEST_SHA256,
                sut.FROZEN_COVERAGE25_MANIFEST_SHA256}) == 3
    assert sut.preview(plan, projection)["manifest_sha256"] == sut.FROZEN_COVERAGE25_MANIFEST_SHA256


@pytest.mark.parametrize("candidate_id,family", [
    ("R222", "relaxed"), ("R222", "weight_ablation"),
    ("R221", "coverage25"), ("R220", "coverage25"), ("R214", "coverage25")])
def test_coverage25_cross_family_plan_refused_before_cloud(coverage25, candidate_id, family):
    plan, projection, fake, _ = coverage25
    with pytest.raises(sut.RelaxedQcSubmissionError):
        sut.launch(dataclasses.replace(plan, candidate_id=candidate_id, family=family), projection, fake)
    assert fake.calls == []


@pytest.mark.parametrize("mutation", ["zero", "extra", "kind", "candidate"])
def test_coverage25_exact_one_hundred_percent_candidate_census(coverage25, monkeypatch, mutation):
    plan, projection, fake, manifest = coverage25
    row = manifest["candidates"][0]
    if mutation == "zero":
        row["tilt_fraction"] = "0.00"
    elif mutation == "extra":
        manifest["candidates"].append(dict(row))
    elif mutation == "kind":
        row["kind"] = "coverage"
    else:
        row["candidate_id"] = "R223"
    sut.COVERAGE25_MANIFEST_PATH.write_bytes(legacy.canonical(manifest))
    monkeypatch.setattr(sut, "FROZEN_COVERAGE25_MANIFEST_SHA256", hashlib.sha256(sut.COVERAGE25_MANIFEST_PATH.read_bytes()).hexdigest())
    with pytest.raises(sut.RelaxedQcSubmissionError, match="census"):
        sut.launch(plan, projection, fake)
    assert fake.calls == []


def test_coverage25_unpinned_refused_before_cloud(coverage25, monkeypatch):
    plan, projection, fake, _ = coverage25
    monkeypatch.setattr(sut, "FROZEN_COVERAGE25_MANIFEST_SHA256", None)
    with pytest.raises(sut.RelaxedQcSubmissionError, match="frozen manifest"):
        sut.launch(plan, projection, fake)
    assert fake.calls == []


def test_coverage25_receipt_refuses_other_family_pin(coverage25):
    plan, projection, fake, _ = coverage25
    launch = sut.launch(plan, projection, fake)
    assert sut._receipt(plan, launch)["manifest_sha256"] == sut.FROZEN_COVERAGE25_MANIFEST_SHA256
    claim = sut.common._read(sut._path(plan, "claim"))
    claim["manifest_sha256"] = sut.FROZEN_ABLATION_MANIFEST_SHA256
    launch["manifest_sha256"] = sut.FROZEN_ABLATION_MANIFEST_SHA256
    sut._path(plan, "claim").write_bytes(legacy.canonical(claim))
    sut._path(plan, "launch").write_bytes(legacy.canonical(launch))
    with pytest.raises(sut.RelaxedQcSubmissionError, match="claim"):
        sut._receipt(plan, launch)


def test_coverage25_three_failed_compiles_reuse_one_project(coverage25):
    plan, projection, fake, _ = coverage25
    fake.compile_state = "BuildError"
    for attempt in (1, 2, 3):
        with pytest.raises(sut.RelaxedQcSubmissionError, match="compile failed"):
            sut.launch(dataclasses.replace(plan, attempt=attempt), projection, fake)
    before = len(fake.calls)
    with pytest.raises(sut.RelaxedQcSubmissionError, match="bound"):
        sut.launch(dataclasses.replace(plan, attempt=4), projection, fake)
    assert len(fake.calls) == before
    assert sum(endpoint == "projects/create" for endpoint, _ in fake.calls) == 1
