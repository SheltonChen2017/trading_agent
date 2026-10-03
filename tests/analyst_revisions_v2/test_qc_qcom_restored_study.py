"""Offline freeze, fake-cloud submission, and parser gates for R248--R259."""

import copy
import hashlib
import json

import pytest

from research.analyst_revisions_v2_qc import six_universe_qcom_restored_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from scripts import run_arv2_qcom_restored as script
from tests.analyst_revisions_v2.test_qc_matched_study_submission import order_statistics
from tests.analyst_revisions_v2.test_qc_relaxed_submission import Fake, ORG, canonical


def manifest():
    return json.loads(adapter.QCOM_RESTORED_MANIFEST_PATH.read_bytes())


def row_for(candidate):
    return next(row for row in manifest()["candidates"] if row["candidate_id"] == candidate)


@pytest.fixture(scope="module")
def exact_projections():
    inputs = script.package()
    return inputs, {candidate: script.projected(candidate, inputs)
                    for candidate in study.CANDIDATES}


def statistics_fixture(row):
    statistics = order_statistics(row)
    aggregate = json.loads(statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"])
    aggregate["analyst_revision_economic_usage"] = row["analyst_revision_economic_usage"]
    if row["coverage_policy_id"] is not None:
        aggregate["coverage_policy_id"] = row["coverage_policy_id"]
    aggregate_raw = canonical(aggregate).decode("ascii")
    statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"] = aggregate_raw
    report = json.loads(statistics[study.excluded.DIAGNOSTIC_NAME])
    report["arm"] = "ar_off" if row["arm"] == "ar_off" else "ar_on100"
    statistics[study.excluded.DIAGNOSTIC_NAME] = canonical(report).decode("ascii")
    meta = json.loads(statistics["ARV2_SIX_GATE_ORDER_META"])
    meta["aggregate_sha256"] = hashlib.sha256(aggregate_raw.encode("ascii")).hexdigest()
    meta["matched_diagnostics_sha256"] = adapter._sha(report)
    statistics["ARV2_SIX_GATE_ORDER_META"] = canonical(meta).decode("ascii")
    return statistics


def _replace_aggregate(statistics, aggregate):
    value = copy.deepcopy(statistics)
    raw = canonical(aggregate).decode("ascii")
    value["ARV2_SIX_GATE_ORDER_AGGREGATES"] = raw
    meta = json.loads(value["ARV2_SIX_GATE_ORDER_META"])
    meta["aggregate_sha256"] = hashlib.sha256(raw.encode("ascii")).hexdigest()
    value["ARV2_SIX_GATE_ORDER_META"] = canonical(meta).decode("ascii")
    return value


def test_manifest_is_exact_separate_twelve_candidate_freeze():
    raw = adapter.QCOM_RESTORED_MANIFEST_PATH.read_bytes()
    value = adapter._qcom_restored_manifest()
    assert hashlib.sha256(raw).hexdigest() == adapter.FROZEN_QCOM_RESTORED_MANIFEST_SHA256
    assert raw == (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("ascii")
    assert list(study.CANDIDATES.items()) == [
        (f"R{new}", f"R{old}") for new, old in zip(range(248, 260), range(235, 247))
    ]
    assert value["protocol"]["maximum_attempts_per_candidate"] == 3
    assert value["protocol"]["physical_orders"] is True
    assert value["protocol"]["sensitivity_only"] is True
    assert value["protocol"]["confirmation"] is False
    assert value["protocol"]["formal_alpha"] is False
    assert value["protocol"]["paper_live_trading"] is False
    assert value["package_sha256"] == study.delta.EXPECTED_DELTA_PACKAGE_SHA256
    assert value["activation_manifest_sha256"] == study.excluded.HISTORICAL_ACTIVATION_SHA256


@pytest.mark.parametrize("defect", (
    "reordered", "old_id", "predecessor", "predecessor_pin", "profile", "source",
    "coverage", "economic_usage", "meta_schema", "summary_schema", "tilt",
    "duplicate_project", "extra_field", "confirmation", "attempts",
))
def test_manifest_refuses_changed_identity_or_economics(defect):
    value = manifest()
    row = value["candidates"][0]
    if defect == "reordered": value["candidates"].reverse()
    elif defect == "old_id": row["candidate_id"] = "R235"
    elif defect == "predecessor": row["predecessor_candidate_id"] = "R236"
    elif defect == "predecessor_pin": row["predecessor_manifest_sha256"] = "f" * 64
    elif defect == "profile": row["profile_sha256"] = "invalid"
    elif defect == "source": row["source_files_sha256"] = "invalid"
    elif defect == "coverage": row["coverage_policy_id"] = "0.10"
    elif defect == "economic_usage": row["analyst_revision_economic_usage"] = "entry_only"
    elif defect == "meta_schema": row["meta_schema"] += "-drift"
    elif defect == "summary_schema": row["summary_schema"] += "-drift"
    elif defect == "tilt": row["tilt_fraction"] = "1.00"
    elif defect == "duplicate_project": value["candidates"][1]["project_name"] = row["project_name"]
    elif defect == "extra_field": row["extra"] = True
    elif defect == "confirmation": value["protocol"]["confirmation"] = True
    elif defect == "attempts": value["protocol"]["maximum_attempts_per_candidate"] = 4
    with pytest.raises(adapter.RelaxedQcSubmissionError):
        study.validate_manifest(value)


def test_frozen_projections_and_offline_previews_for_all_twelve(
    exact_projections, monkeypatch, tmp_path,
):
    inputs, projections = exact_projections
    value = manifest()
    monkeypatch.setattr(script, "package", lambda: inputs)
    monkeypatch.setattr(script, "projected", lambda candidate, unused=None: projections[candidate])
    assert script.freeze() == value
    for row in value["candidates"]:
        candidate = row["candidate_id"]
        projection, profile = projections[candidate]
        files = [[item.project_path, item.content_sha256, item.byte_count]
                 for item in projection.source_files]
        assert projection.projection_sha256 == row["projection_sha256"]
        assert projection.profile_sha256 == row["profile_sha256"] == profile["profile_sha256"]
        assert projection.role == row["role"]
        assert profile["matched_baseline_profile_sha256"] == row["matched_baseline_profile_sha256"]
        assert profile.get("coverage_policy_id") == row["coverage_policy_id"]
        assert not {"stock_exclusion_policy_id", "excluded_logical_security_sha256"} & set(profile)
        assert hashlib.sha256(canonical(files)).hexdigest() == row["source_files_sha256"]
        for attempt in (1, 2, 3):
            plan = adapter.build_plan(
                candidate, ORG, tmp_path / "controls", attempt, family=study.FAMILY,
            )
            assert adapter.preview(plan, projection)["manifest_sha256"] == (
                adapter.FROZEN_QCOM_RESTORED_MANIFEST_SHA256
            )
        with pytest.raises(adapter.RelaxedQcSubmissionError, match="bound"):
            adapter.build_plan(candidate, ORG, tmp_path / "controls", 4, family=study.FAMILY)


@pytest.mark.parametrize("candidate", tuple(study.CANDIDATES))
def test_parser_accepts_each_exact_arm_and_refuses_exclusion_fields(candidate, tmp_path):
    row = row_for(candidate)
    plan = adapter.build_plan(candidate, ORG, tmp_path / "controls", family=study.FAMILY)
    statistics = statistics_fixture(row)
    parsed = study.parse_order(plan, statistics)
    assert parsed["run_valid"] is True
    assert parsed["meta"]["schema"] == row["meta_schema"]
    assert parsed["aggregates"]["schema"] == row["summary_schema"]
    assert parsed["aggregates"]["analyst_revision_economic_usage"] == (
        row["analyst_revision_economic_usage"]
    )
    assert not {"stock_exclusion_policy_id", "excluded_logical_security_sha256"} & (
        parsed["aggregates"].keys()
    )
    aggregate = json.loads(statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"])
    aggregate["stock_exclusion_policy_id"] = "historical_QCOM_exclusion"
    with pytest.raises(adapter.RelaxedQcSubmissionError):
        study.parse_order(plan, _replace_aggregate(statistics, aggregate))


@pytest.mark.parametrize("candidate", ("R248", "R251", "R255", "R259"))
def test_fake_cloud_launch_and_one_bounded_read(
    candidate, exact_projections, tmp_path, monkeypatch,
):
    monkeypatch.setattr(adapter, "_require_inputs", lambda plan: None)
    monkeypatch.setattr(adapter.common, "_client", lambda api: None)
    fake = Fake()
    monkeypatch.setattr(adapter.common, "_post", fake.post)
    projection = exact_projections[1][candidate][0]
    plan = adapter.build_plan(candidate, ORG, tmp_path / "controls", family=study.FAMILY)
    receipt = adapter.launch(plan, projection, fake)
    assert receipt["candidate_id"] == candidate and receipt["attempt"] == 1
    assert receipt["project_name"] == row_for(candidate)["project_name"]
    assert [endpoint for endpoint, _ in fake.calls].count("backtests/create") == 1
    fake.status = "Completed."
    assert adapter.poll_status(plan, receipt, fake) == "Completed."
    fake.statistics = {**statistics_fixture(row_for(candidate)), "Net Profit": "NOT RETAINED"}
    parsed = adapter.read_result_once(plan, receipt, fake)
    assert parsed["run_valid"] is True
    assert "NOT RETAINED" not in repr(parsed)
    assert [endpoint for endpoint, _ in fake.calls].count("backtests/read") == 1
    with pytest.raises(adapter.common.SixUniverseSettlementSubmissionError):
        adapter.read_result_once(plan, receipt, fake)


@pytest.mark.parametrize("defect", (
    "meta_schema", "economic_usage", "coverage_policy", "excluded_logical_security",
))
def test_parser_refuses_changed_writer_or_policy(defect, tmp_path):
    candidate = "R251" if defect == "coverage_policy" else "R259"
    row = row_for(candidate)
    plan = adapter.build_plan(candidate, ORG, tmp_path / "controls", family=study.FAMILY)
    statistics = statistics_fixture(row)
    if defect == "meta_schema":
        meta = json.loads(statistics["ARV2_SIX_GATE_ORDER_META"])
        meta["schema"] = "arv2-six-matched-qcom-excluded-meta-v1"
        statistics["ARV2_SIX_GATE_ORDER_META"] = canonical(meta).decode("ascii")
    else:
        aggregate = json.loads(statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"])
        if defect == "economic_usage": aggregate["analyst_revision_economic_usage"] = "entry_count_and_weight"
        elif defect == "coverage_policy": aggregate["coverage_policy_id"] = "wrong"
        else: aggregate["excluded_logical_security_sha256"] = "f" * 64
        statistics = _replace_aggregate(statistics, aggregate)
    with pytest.raises(adapter.RelaxedQcSubmissionError):
        study.parse_order(plan, statistics)
