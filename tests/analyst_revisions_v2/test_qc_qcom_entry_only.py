"""Offline behavioural proof for the one historical AR-entry-only order arm."""

import copy
from decimal import Decimal
import hashlib
import json

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_matched_historical_projection as prior
from research.analyst_revisions_v2_qc import six_universe_qcom_entry_only_projection as subject
from research.analyst_revisions_v2_qc import six_universe_qcom_entry_only_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from tests.analyst_revisions_v2.test_qc_matched_historical_projection import package
from tests.analyst_revisions_v2.test_qc_relaxed_selection_source import _rows, _snapshots
from tests.analyst_revisions_v2.test_qc_qcom_exclusion_tilt_study import statistics_fixture
from tests.analyst_revisions_v2.test_qc_qcom_exclusion_study import result_fixture
from tests.analyst_revisions_v2.test_qc_relaxed_submission import Fake, ORG, canonical


def _sources(value):
    return {item.project_path: item.source_bytes.decode("ascii") for item in value.source_files}


@pytest.fixture(scope="module")
def family(package):
    return (prior.build_qcom_exclusion_projection(package, "ar_on100", 0),
            subject.build_qcom_entry_only_projection(package))


def test_exact_r232_source_gate_and_new_order_identity(family):
    (old, old_profile), (new, profile) = family
    assert old.projection_sha256 == subject.PREDECESSOR_PROJECTION_SHA256
    assert new.projection_sha256 == study.EXPECTED_PROJECTION_SHA256
    assert profile["profile_sha256"] == new.profile_sha256 == study.EXPECTED_PROFILE_SHA256
    assert profile["role"] == new.role == "matched_qcom_excluded_ar_on0_s0"
    assert profile["comparison_arm"] == "ar_on0"
    assert profile["analyst_revision_economic_usage"] == subject.ECONOMIC_USAGE
    assert profile["maximum_stock_weight_change_fraction"] == "0.00"
    assert profile["matched_baseline_profile_sha256"] == old_profile[
        "matched_baseline_profile_sha256"] == study.EXPECTED_BASELINE_PROFILE_SHA256
    assert profile["target_gross_exposure"] == "0.98"
    assert profile["admission_leverage"] == "2"
    assert profile["slippage_bps"] == "0"
    assert profile["modeled_fee_bps_per_side"] == "10"
    assert new.package_sha256 == old.package_sha256
    assert new.activation_manifest_sha256 == old.activation_manifest_sha256
    before, after = _sources(old), _sources(new)
    assert set(before) == set(after) and len(after) == 17
    assert {name for name in before if before[name] != after[name]} == {
        "accepted_risk_six_universe_order_tilt_targets.py",
        "accepted_risk_six_universe_order_tilt_qc_runtime.py", "main.py"}
    assert after["accepted_risk_six_universe_gate.py"] == before["accepted_risk_six_universe_gate.py"]
    assert after["accepted_risk_six_universe_order_targets.py"] == before[
        "accepted_risk_six_universe_order_targets.py"]
    assert after["accepted_risk_matched_diagnostics.py"] == before[
        "accepted_risk_matched_diagnostics.py"]
    with subject.relaxed._cloud_loader(after) as (load, _):
        runtime = load(subject.relaxed._TILT_RUNTIME_PATH[:-3])
        gate = load(subject.relaxed._GATE_PATH[:-3])
        assert runtime.require_tilt_profile() == profile
        assert gate.MINIMUM_POSITIVE_SCORE_COUNT == 5
        assert runtime.TILT_SUMMARY_SCHEMA == "arv2-six-matched-qcom-excluded-tilt0-summary-v1"
        assert load("accepted_risk_six_universe_order_qc_runtime").META_SCHEMA == (
            prior.QCOM_EXCLUSION_META_SCHEMA)


def test_emitted_meta_uses_shared_order_schema_not_tilt_module_schema(family):
    (_, _), (value, _) = family
    row = adapter._qcom_entry_only_manifest()["candidates"][0]
    with subject.relaxed._cloud_loader(_sources(value)) as (load, _):
        base = load("accepted_risk_six_universe_order_qc_runtime")
        bridge = load("accepted_risk_six_universe_order_bridge_qc_runtime")
        tilt = load("accepted_risk_six_universe_order_tilt_qc_runtime")
        inherited_writer = tilt.AcceptedRiskSixUniverseOrderTiltQcDriver.on_end_of_algorithm
        assert inherited_writer is bridge.BridgeAdmissionMixin.on_end_of_algorithm
        assert inherited_writer.__globals__["_base"] is base
        assert base.META_SCHEMA == row["meta_schema"]
        assert tilt.TILT_META_SCHEMA != row["meta_schema"]


@pytest.mark.parametrize("positive_count", (0, 4, 5, 8, 12))
def test_positive_score_admission_count_is_identical_to_r232_and_zero_transfer(
        family, positive_count):
    (old, _), (new, _) = family
    observations = []
    for value in (old, new):
        with subject.relaxed._cloud_loader(_sources(value)) as (load, _):
            tilt = load("accepted_risk_six_universe_order_tilt_targets")
            gate = tilt._gate
            snapshots = _snapshots(gate, {"QQQ": _rows(gate, "QQQ", positives=positive_count)})
            construction = gate.build_six_universe_construction(
                snapshots, gate.TOP10_CAP90_EXPLORATORY_PROFILE)
            qqq = next(item for item in construction.sleeves if item.universe_id == "QQQ")
            observations.append((qqq.positive_score_count, qqq.matched_security_ids,
                                 qqq.matched_etf_fallback_weight))
            if value is new:
                assert tilt.MAXIMUM_STOCK_WEIGHT_CHANGE_FRACTION == Decimal("0.00")
                assert tilt.tilt_matched_weights(construction, snapshots) == construction.matched_weights
                assert len(qqq.matched_security_ids) == (
                    0 if positive_count < 5 else min(positive_count, 10))
    assert observations[0] == observations[1]


def test_one_pinned_manifest_previews_exact_candidate_without_qc(family, tmp_path):
    from scripts import run_arv2_qcom_entry_only as script
    (old, _), (value, profile) = family
    raw = adapter.QCOM_ENTRY_ONLY_MANIFEST_PATH.read_bytes()
    manifest = json.loads(raw)
    assert hashlib.sha256(raw).hexdigest() == adapter.FROZEN_QCOM_ENTRY_ONLY_MANIFEST_SHA256
    assert raw == (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("ascii")
    assert study.validate_manifest(manifest) == manifest
    assert [row["candidate_id"] for row in manifest["candidates"]] == ["R246"]
    assert manifest["protocol"]["control_manifest_sha256"] == adapter.FROZEN_QCOM_EXCLUSION_MANIFEST_SHA256
    row = manifest["candidates"][0]
    assert row["projection_sha256"] == value.projection_sha256
    assert row["profile_sha256"] == profile["profile_sha256"]
    assert row["source_file_count"] == len(value.source_files)
    assert row["total_source_bytes"] == value.total_source_byte_count
    assert row["source_files_sha256"] == adapter._sha([
        [item.project_path, item.content_sha256, item.byte_count]
        for item in value.source_files])
    assert old.profile_sha256 != value.profile_sha256
    plan = adapter.build_plan("R246", "a" * 32, tmp_path / "control", family=study.FAMILY)
    assert adapter.preview(plan, value)["projection_sha256"] == value.projection_sha256
    assert script.freeze() == manifest
    for invalid in (0, 4, True, "2"):
        with pytest.raises(adapter.RelaxedQcSubmissionError, match="bound"):
            adapter.build_plan("R246", "a" * 32, tmp_path / "control", invalid,
                               family=study.FAMILY)


@pytest.mark.parametrize("change", ("extra", "arm", "candidate", "tilt", "source", "protocol"))
def test_manifest_refuses_changed_identity(change):
    value = copy.deepcopy(adapter._qcom_entry_only_manifest())
    row = value["candidates"][0]
    if change == "extra":
        row["unchecked"] = 1
    elif change == "arm":
        row["arm"] = "ar_off"
    elif change == "candidate":
        row["candidate_id"] = "R232"
    elif change == "tilt":
        row["tilt_fraction"] = "1.00"
    elif change == "source":
        row["projection_sha256"] = "f" * 64
    else:
        value["protocol"]["selection_policy"] = "unknown"
    with pytest.raises(adapter.RelaxedQcSubmissionError):
        study.validate_manifest(value)


def test_predecessor_or_usage_anchor_change_refuses_before_qc(package, monkeypatch):
    monkeypatch.setattr(subject, "PREDECESSOR_PROJECTION_SHA256", "f" * 64)
    with pytest.raises(subject.QcomEntryOnlyProjectionError, match="predecessor"):
        subject.build_qcom_entry_only_projection(package)
    monkeypatch.setattr(subject, "PREDECESSOR_PROJECTION_SHA256",
                        "87c3ecd2a36522f101086afeaf0bf19758757267f59035db2fb169e23bd3e803")
    original = prior._render_qcom_exclusion_tilt
    def changed(path, source, percent):
        text = original(path, source, percent)
        return text.replace("entry_count_and_weight", "unspecified")
    monkeypatch.setattr(prior, "_render_qcom_exclusion_tilt", changed)
    with pytest.raises(subject.QcomEntryOnlyProjectionError, match="disclosure anchor"):
        subject.build_qcom_entry_only_projection(package)


def _statistics(row):
    statistics = statistics_fixture(row)
    aggregate = json.loads(statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"])
    aggregate["analyst_revision_economic_usage"] = subject.ECONOMIC_USAGE
    raw = canonical(aggregate).decode("ascii")
    statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"] = raw
    meta = json.loads(statistics["ARV2_SIX_GATE_ORDER_META"])
    meta["aggregate_sha256"] = hashlib.sha256(raw.encode("ascii")).hexdigest()
    statistics["ARV2_SIX_GATE_ORDER_META"] = canonical(meta).decode("ascii")
    return statistics


def test_fake_cloud_one_attempt_one_bounded_read_and_economic_mode_refusal(
        family, tmp_path, monkeypatch):
    row = adapter._qcom_entry_only_manifest()["candidates"][0]
    plan = adapter.build_plan("R246", ORG, tmp_path / "control", family=study.FAMILY)
    monkeypatch.setattr(adapter, "_require_inputs", lambda plan: None)
    monkeypatch.setattr(adapter.common, "_client", lambda api: None)
    fake = Fake()
    monkeypatch.setattr(adapter.common, "_post", fake.post)
    statistics = _statistics(row)
    assert adapter._parse_order(plan, statistics)["aggregates"][
        "analyst_revision_economic_usage"] == subject.ECONOMIC_USAGE
    wrong = copy.deepcopy(statistics)
    aggregate = json.loads(wrong["ARV2_SIX_GATE_ORDER_AGGREGATES"])
    aggregate["analyst_revision_economic_usage"] = "entry_count_and_weight"
    raw = canonical(aggregate).decode("ascii")
    wrong["ARV2_SIX_GATE_ORDER_AGGREGATES"] = raw
    meta = json.loads(wrong["ARV2_SIX_GATE_ORDER_META"])
    meta["aggregate_sha256"] = hashlib.sha256(raw.encode("ascii")).hexdigest()
    wrong["ARV2_SIX_GATE_ORDER_META"] = canonical(meta).decode("ascii")
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="economic mode"):
        adapter._parse_order(plan, wrong)
    receipt = adapter.launch(plan, family[1][0], fake)
    fake.status = "Completed."
    assert adapter.poll_status(plan, receipt, fake) == "Completed."
    fake.statistics = {**statistics, "Net Profit": "NOT RETAINED"}
    result = adapter.read_result_once(plan, receipt, fake)
    assert result["run_valid"] is True
    assert result["aggregates"]["analyst_revision_economic_usage"] == subject.ECONOMIC_USAGE
    assert "NOT RETAINED" not in str(result)
    assert sum(endpoint == "backtests/create" for endpoint, _ in fake.calls) == 1
    assert sum(endpoint == "backtests/read" for endpoint, _ in fake.calls) == 1
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="consumed"):
        adapter.launch(plan, family[1][0], fake)


def test_three_way_comparison_requires_identical_ar_on_baseline_path():
    old_results = result_fixture()
    results = {}
    rows = {row["candidate_id"]: row for row in adapter._qcom_exclusion_manifest()["candidates"]}
    rows["R246"] = adapter._qcom_entry_only_manifest()["candidates"][0]
    for candidate, original in (("R231", old_results["R231"]),
                                ("R246", old_results["R232"]),
                                ("R232", old_results["R232"])):
        result = copy.deepcopy(original)
        result.update(candidate_id=candidate, attempt=1, status="Completed.",
            run_valid=True,
            manifest_sha256=(adapter.FROZEN_QCOM_ENTRY_ONLY_MANIFEST_SHA256
                if candidate == "R246" else adapter.FROZEN_QCOM_EXCLUSION_MANIFEST_SHA256),
            projection_sha256=rows[candidate]["projection_sha256"])
        result["aggregates"].update(
            matched_baseline_profile_sha256=rows[candidate]["matched_baseline_profile_sha256"],
            maximum_stock_weight_change_fraction=rows[candidate]["tilt_fraction"])
        if candidate == "R246":
            result["aggregates"].update(comparison_arm="ar_on0",
                maximum_stock_weight_change_fraction="0.00",
                analyst_revision_economic_usage=subject.ECONOMIC_USAGE)
        results[candidate] = result
    result = study.compare_results(results)
    assert result["comparison_valid"] is True
    assert result["spreads"] == {
        "AR_entry_count_vs_off_percentage_points": "5.00",
        "AR_weight_given_same_entry_percentage_points": "0.00",
        "AR_total_vs_off_percentage_points": "5.00",
    }
    wrong = copy.deepcopy(results)
    wrong["R246"]["aggregates"]["matched_baseline_target_path_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="baseline holdings differ"):
        study.compare_results(wrong)
