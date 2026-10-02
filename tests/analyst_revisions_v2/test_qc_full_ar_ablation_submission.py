"""Isolate full AR on/off family identity and bounded fake-cloud operations."""

import dataclasses
import hashlib

import pytest

from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as sut
from tests.analyst_revisions_v2 import test_qc_relaxed_submission as legacy
from tests.analyst_revisions_v2.test_qc_relaxed_ablation_submission import ablation


@pytest.fixture
def full_ar(ablation, monkeypatch):
    plan, projection, fake, predecessor = ablation
    rows = [
        {**row, "candidate_id": candidate, "project_name": "ARV2 TEST " + candidate,
         "backtest_name": "ARV2 TEST " + candidate, "analyst_revision_enabled": enabled,
         "meta_schema": "test-full-ar-meta-" + str(enabled),
         "summary_schema": "test-full-ar-summary-" + str(enabled)}
        for row, candidate, enabled in zip(predecessor["candidates"],
                                           ("R223", "R224"), (False, True))]
    manifest = {**predecessor, "schema": "test-full-ar-family", "candidates": rows}
    path = plan.control_directory.parent / "full_ar.json"
    path.write_bytes(legacy.canonical(manifest))
    monkeypatch.setattr(sut, "FULL_AR_ABLATION_MANIFEST_PATH", path)
    monkeypatch.setattr(sut, "FROZEN_FULL_AR_ABLATION_MANIFEST_SHA256",
                        hashlib.sha256(path.read_bytes()).hexdigest())
    plan = sut.build_plan("R223", legacy.ORG, plan.control_directory,
                          family="full_ar_ablation")
    return plan, projection, fake, manifest


def test_full_ar_preview_has_separate_family_pin_and_exact_modes(full_ar):
    plan, projection, _, _ = full_ar
    identity = sut.preview(plan, projection)
    assert identity["manifest_sha256"] == sut.FROZEN_FULL_AR_ABLATION_MANIFEST_SHA256
    assert identity["manifest_sha256"] not in {
        sut.FROZEN_MANIFEST_SHA256, sut.FROZEN_ABLATION_MANIFEST_SHA256,
        sut.FROZEN_COVERAGE25_MANIFEST_SHA256}
    assert sut._candidate(plan)["analyst_revision_enabled"] is False
    assert sut._candidate(dataclasses.replace(plan, candidate_id="R224"))[
        "analyst_revision_enabled"] is True


@pytest.mark.parametrize("candidate,family", [
    ("R223", "relaxed"), ("R223", "weight_ablation"), ("R223", "coverage25"),
    ("R224", "relaxed"), ("R224", "coverage25"),
    ("R222", "full_ar_ablation"), ("R221", "full_ar_ablation"),
    ("R214", "full_ar_ablation"), ("R223", True)])
def test_full_ar_cross_family_refused_before_external_io(full_ar, candidate, family):
    plan, projection, fake, _ = full_ar
    with pytest.raises(sut.RelaxedQcSubmissionError):
        sut.launch(dataclasses.replace(plan, candidate_id=candidate, family=family),
                   projection, fake)
    assert fake.calls == []


@pytest.mark.parametrize("mutation", ["ids", "fractions", "kind", "extra",
                                       "off_enabled", "on_disabled", "mode_number"])
def test_full_ar_authenticated_manifest_requires_exact_census(full_ar, monkeypatch, mutation):
    plan, projection, fake, manifest = full_ar
    rows = manifest["candidates"]
    if mutation == "ids":
        rows[0]["candidate_id"] = "R225"
    elif mutation == "fractions":
        rows[0]["tilt_fraction"] = "0.20"
    elif mutation == "kind":
        rows[0]["kind"] = "coverage"
    elif mutation == "extra":
        rows.append(dict(rows[0]))
    elif mutation == "off_enabled":
        rows[0]["analyst_revision_enabled"] = True
    elif mutation == "on_disabled":
        rows[1]["analyst_revision_enabled"] = False
    else:
        rows[0]["analyst_revision_enabled"] = 0
    sut.FULL_AR_ABLATION_MANIFEST_PATH.write_bytes(legacy.canonical(manifest))
    monkeypatch.setattr(sut, "FROZEN_FULL_AR_ABLATION_MANIFEST_SHA256",
        hashlib.sha256(sut.FULL_AR_ABLATION_MANIFEST_PATH.read_bytes()).hexdigest())
    with pytest.raises(sut.RelaxedQcSubmissionError, match="census"):
        sut.launch(plan, projection, fake)
    assert fake.calls == []


def test_full_ar_unpinned_manifest_refused(full_ar, monkeypatch):
    plan, projection, fake, _ = full_ar
    monkeypatch.setattr(sut, "FROZEN_FULL_AR_ABLATION_MANIFEST_SHA256", None)
    with pytest.raises(sut.RelaxedQcSubmissionError, match="frozen manifest"):
        sut.launch(plan, projection, fake)
    assert fake.calls == []


def test_full_ar_changed_manifest_refused_before_cloud(full_ar):
    plan, projection, fake, _ = full_ar
    sut.FULL_AR_ABLATION_MANIFEST_PATH.write_bytes(b"{}")
    with pytest.raises(sut.RelaxedQcSubmissionError, match="frozen manifest"):
        sut.launch(plan, projection, fake)
    assert fake.calls == []


@pytest.mark.parametrize("attribute", ["role", "schema", "profile_sha256"])
def test_full_ar_preview_refuses_changed_projection_identity(full_ar, attribute):
    plan, projection, fake, _ = full_ar
    setattr(projection, attribute, "changed")
    with pytest.raises(sut.RelaxedQcSubmissionError, match="projection"):
        sut.launch(plan, projection, fake)
    assert fake.calls == []


def test_full_ar_three_failed_compiles_spend_slots_in_one_project(full_ar):
    plan, projection, fake, _ = full_ar
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


def test_full_ar_receipt_refuses_other_family_pin(full_ar):
    plan, projection, fake, _ = full_ar
    launch = sut.launch(plan, projection, fake)
    assert sut._receipt(plan, launch)["manifest_sha256"] == sut.FROZEN_FULL_AR_ABLATION_MANIFEST_SHA256
    claim = sut.common._read(sut._path(plan, "claim"))
    claim["manifest_sha256"] = sut.FROZEN_ABLATION_MANIFEST_SHA256
    launch["manifest_sha256"] = sut.FROZEN_ABLATION_MANIFEST_SHA256
    sut._path(plan, "claim").write_bytes(legacy.canonical(claim))
    sut._path(plan, "launch").write_bytes(legacy.canonical(launch))
    with pytest.raises(sut.RelaxedQcSubmissionError, match="claim"):
        sut._receipt(plan, launch)


def test_full_ar_launch_and_result_read_each_one_use(full_ar, monkeypatch):
    plan, projection, fake, _ = full_ar
    launch = sut.launch(plan, projection, fake)
    with pytest.raises(sut.RelaxedQcSubmissionError, match="consumed"):
        sut.launch(plan, projection, fake)
    fake.status = "Completed."
    sut.poll_status(plan, launch, fake)
    fake.statistics = {name: "{}" for name in sut._candidate(plan)["statistic_names"]}
    monkeypatch.setattr(sut, "_parse_order", lambda plan, statistics: {"run_valid": True})
    assert sut.read_result_once(plan, launch, fake)["run_valid"] is True
    assert sut._read_artifact(sut._path(plan, "result"))["manifest_sha256"] == sut.FROZEN_FULL_AR_ABLATION_MANIFEST_SHA256
    with pytest.raises(sut.common.SixUniverseSettlementSubmissionError):
        sut.read_result_once(plan, launch, fake)
    assert sum(endpoint == "backtests/read" for endpoint, _ in fake.calls) == 1


def test_full_ar_cannot_inherit_historical_transport_recovery(full_ar):
    plan, projection, fake, _ = full_ar
    launch = sut.launch(plan, projection, fake)
    fake.status = "Completed."
    sut.poll_status(plan, launch, fake)
    with pytest.raises(sut.RelaxedQcSubmissionError, match="recovery"):
        sut.read_result_once(plan, launch, fake, recover_r209_transport=True)
    assert not any(endpoint == "backtests/read" for endpoint, _ in fake.calls)


@pytest.mark.parametrize("candidate_id", ["R223", "R224"])
def test_full_ar_real_parser_authenticates_mode_profile_schema_and_fraction(full_ar, candidate_id):
    plan, _, _, _ = full_ar
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
    opposite = "R224" if candidate_id == "R223" else "R223"
    with pytest.raises(sut.RelaxedQcSubmissionError, match="metadata"):
        sut._parse_order(dataclasses.replace(plan, candidate_id=opposite), stats)
    aggregate["maximum_stock_weight_change_fraction"] = "0.20"
    raw = legacy.canonical(aggregate).decode("ascii")
    meta["aggregate_sha256"] = hashlib.sha256(raw.encode("ascii")).hexdigest()
    stats.update(ARV2_SIX_GATE_ORDER_META=legacy.canonical(meta).decode("ascii"),
                 ARV2_SIX_GATE_ORDER_AGGREGATES=raw)
    with pytest.raises(sut.RelaxedQcSubmissionError, match="aggregate identity"):
        sut._parse_order(plan, stats)
