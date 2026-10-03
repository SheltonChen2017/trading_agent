"""Offline source, pilot stop, three-attempt and bounded-result gates."""

import copy
import hashlib
import json

import pytest

from research.analyst_revisions_v2_qc import six_universe_qcom_score_floor1_study as study
from research.analyst_revisions_v2_qc import six_universe_relaxed_submission as adapter
from scripts import run_arv2_qcom_score_floor1 as script
from tests.analyst_revisions_v2.test_qc_matched_study_submission import order_statistics
from tests.analyst_revisions_v2.test_qc_relaxed_submission import Fake, ORG, canonical


def manifest():
    return json.loads(adapter.QCOM_SCORE_FLOOR1_MANIFEST_PATH.read_bytes())


def row_for(candidate):
    return next(row for row in manifest()["candidates"] if row["candidate_id"] == candidate)


@pytest.fixture(scope="module")
def exact_projections():
    inputs = script.package()
    return inputs, {candidate: script.projected(candidate, inputs)
                    for candidate in study.CANDIDATE_PERCENTS}


def statistics_fixture(row):
    statistics = order_statistics(row)
    aggregate = json.loads(statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"])
    aggregate["analyst_revision_economic_usage"] = "entry_count_and_weight"
    aggregate["coverage_policy_id"] = study.COVERAGE_POLICY_ID
    aggregate_raw = canonical(aggregate).decode("ascii")
    statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"] = aggregate_raw
    report = json.loads(statistics[study.excluded.DIAGNOSTIC_NAME])
    report["arm"] = row["arm"]
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


def test_manifest_is_exact_seven_arm_pilot_first_freeze():
    raw = adapter.QCOM_SCORE_FLOOR1_MANIFEST_PATH.read_bytes()
    value = adapter._qcom_score_floor1_manifest()
    assert hashlib.sha256(raw).hexdigest() == adapter.FROZEN_QCOM_SCORE_FLOOR1_MANIFEST_SHA256
    assert raw == (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("ascii")
    assert list(study.CANDIDATE_PERCENTS.values()) == [80, 100, 120, 140, 160, 180, 200]
    assert list(study.CANDIDATE_PERCENTS) == [f"R{number}" for number in range(260, 267)]
    assert value["protocol"]["pilot_candidate_id"] == "R261"
    assert value["protocol"]["pilot_required_remx_post_cap_stock_target_count_at_least"] == 1
    assert value["protocol"]["pilot_required_total_post_cap_stock_target_count_above"] == 12211
    assert value["protocol"]["maximum_attempts_per_candidate"] == 3
    assert value["protocol"]["physical_orders"] is True
    assert value["protocol"]["formal_alpha"] is False
    assert value["protocol"]["paper_live_trading"] is False


@pytest.mark.parametrize("defect", (
    "old_id", "source_pin", "wrong_floor", "wrong_tilt", "wrong_arm",
    "writer_meta", "writer_summary", "coverage", "source_hash", "duplicate_project",
    "four_attempts", "no_pilot_gate", "extra_field",
))
def test_manifest_refuses_changed_rule_source_or_lineage(defect):
    value = manifest()
    row = value["candidates"][0]
    if defect == "old_id": row["candidate_id"] = "R256"
    elif defect == "source_pin": row["source_projection_sha256"] = "f" * 64
    elif defect == "wrong_floor": row["minimum_positive_score_count"] = 2
    elif defect == "wrong_tilt": row["tilt_fraction"] = "1.20"
    elif defect == "wrong_arm": row["arm"] = "ar_on120"
    elif defect == "writer_meta": row["meta_schema"] += "-drift"
    elif defect == "writer_summary": row["summary_schema"] += "-drift"
    elif defect == "coverage": row["coverage_policy_id"] = "floor2"
    elif defect == "source_hash": row["source_files_sha256"] = "invalid"
    elif defect == "duplicate_project": value["candidates"][1]["project_name"] = row["project_name"]
    elif defect == "four_attempts": value["protocol"]["maximum_attempts_per_candidate"] = 4
    elif defect == "no_pilot_gate": value["protocol"]["pilot_required_total_post_cap_stock_target_count_above"] = 0
    elif defect == "extra_field": row["extra"] = True
    with pytest.raises(adapter.RelaxedQcSubmissionError):
        study.validate_manifest(value)


def test_all_seven_exact_projections_preview_without_qc_io(exact_projections, tmp_path):
    inputs, projections = exact_projections
    assert script.freeze() == manifest()
    for candidate, percent in study.CANDIDATE_PERCENTS.items():
        row = row_for(candidate)
        projection, profile = projections[candidate]
        assert projection.projection_sha256 == row["projection_sha256"]
        assert projection.profile_sha256 == row["profile_sha256"] == profile["profile_sha256"]
        assert projection.role == row["role"]
        assert profile["coverage_policy_id"] == study.COVERAGE_POLICY_ID
        assert profile["maximum_stock_weight_change_fraction"] == row["tilt_fraction"]
        assert profile["matched_baseline_profile_sha256"] == row["matched_baseline_profile_sha256"]
        for attempt in (1, 2, 3):
            plan = adapter.build_plan(candidate, ORG, tmp_path / "controls", attempt,
                                      family=study.FAMILY)
            assert adapter.preview(plan, projection)["manifest_sha256"] == (
                adapter.FROZEN_QCOM_SCORE_FLOOR1_MANIFEST_SHA256
            )
        with pytest.raises(adapter.RelaxedQcSubmissionError, match="bound"):
            adapter.build_plan(candidate, ORG, tmp_path / "controls", 4,
                               family=study.FAMILY)


@pytest.mark.parametrize("candidate", tuple(study.CANDIDATE_PERCENTS))
def test_parser_accepts_exact_new_diagnostic_arm_and_refuses_mismatch(candidate, tmp_path):
    row = row_for(candidate)
    plan = adapter.build_plan(candidate, ORG, tmp_path / "controls", family=study.FAMILY)
    statistics = statistics_fixture(row)
    parsed = study.parse_order(plan, statistics)
    assert parsed["run_valid"] is True
    assert parsed["diagnostics"]["arm"] == row["arm"]
    assert parsed["aggregates"]["comparison_arm"] == row["arm"]
    report = json.loads(statistics[study.excluded.DIAGNOSTIC_NAME])
    report["arm"] = "ar_on100" if row["arm"] != "ar_on100" else "ar_on80"
    changed = copy.deepcopy(statistics)
    changed[study.excluded.DIAGNOSTIC_NAME] = canonical(report).decode("ascii")
    meta = json.loads(changed["ARV2_SIX_GATE_ORDER_META"])
    meta["matched_diagnostics_sha256"] = adapter._sha(report)
    changed["ARV2_SIX_GATE_ORDER_META"] = canonical(meta).decode("ascii")
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="diagnostic arm"):
        study.parse_order(plan, changed)


def test_parser_refuses_rebound_coverage_and_qcom_exclusion(tmp_path):
    row = row_for("R261")
    plan = adapter.build_plan("R261", ORG, tmp_path / "controls", family=study.FAMILY)
    statistics = statistics_fixture(row)
    for key, value in (("coverage_policy_id", "floor2"),
                       ("stock_exclusion_policy_id", "qcom_excluded")):
        aggregate = json.loads(statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"])
        aggregate[key] = value
        with pytest.raises(adapter.RelaxedQcSubmissionError):
            study.parse_order(plan, _replace_aggregate(statistics, aggregate))


def _count_only_result(remx, total):
    fields = [
        "universe_id", "etf_ticker", "decision_count", "coverage_valid_count",
        "coverage_invalid_count", "positive_score_count_sum",
        "selected_security_count_sum", "post_cap_stock_target_count_sum",
        "etf_target_weight_sum", "duplicate_cap_excess_weight_sum",
        "coverage_refusal_reason_counts", "selection_status_counts",
    ]
    baseline = {"SPY": 2520, "QQQ": 2490, "SOXX": 2161,
                "XLV": 2520, "REMX": remx, "XLE": 2520}
    assert sum(baseline.values()) == total
    rows = [[name, name, 261, 0, 0, 0, 0, count, "0", "0", {}, {}]
            for name, count in baseline.items()]
    return {"run_valid": True, "aggregates": {"sleeve_diagnostics": {
        "fields": fields, "rows": rows,
    }}}


def _pilot_statistics(row, remx):
    """An exact bounded parser fixture with a pinned six-sleeve count axis."""
    statistics = statistics_fixture(row)
    aggregate = json.loads(statistics["ARV2_SIX_GATE_ORDER_AGGREGATES"])
    counts = (2520, 2490, 2161, 2520, remx, 2520)
    for sleeve, count in zip(aggregate["sleeve_diagnostics"]["rows"], counts):
        sleeve[6] = count
        sleeve[7] = count
    return _replace_aggregate(statistics, aggregate)


def test_pilot_count_gate_uses_only_exact_sanitized_post_cap_aggregates():
    assert study.pilot_post_cap_stock_target_counts(_count_only_result(1, 12212)) == (1, 12212)
    assert study.pilot_post_cap_stock_target_counts(_count_only_result(0, 12211)) == (0, 12211)
    changed = _count_only_result(1, 12212)
    changed["aggregates"]["sleeve_diagnostics"]["fields"][7] = "selected_security_ids"
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="census"):
        study.pilot_post_cap_stock_target_counts(changed)


def test_nonpilot_launch_refuses_before_any_qc_action_without_pilot(
    exact_projections, tmp_path, monkeypatch,
):
    fake = Fake()
    monkeypatch.setattr(adapter, "_require_inputs", lambda plan: None)
    monkeypatch.setattr(adapter.common, "_client", lambda api: None)
    monkeypatch.setattr(adapter.common, "_post", fake.post)
    plan = adapter.build_plan("R260", ORG, tmp_path / "controls", family=study.FAMILY)
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="pilot"):
        adapter.launch(plan, exact_projections[1]["R260"][0], fake)
    assert fake.calls == []


@pytest.mark.parametrize("remx,total,allowed", (
    (0, 12211, False), (1, 12212, True),
))
def test_pilot_receipt_bound_stop_gate(
    remx, total, allowed, exact_projections, tmp_path, monkeypatch,
):
    fake = Fake()
    monkeypatch.setattr(adapter, "_require_inputs", lambda plan: None)
    monkeypatch.setattr(adapter.common, "_client", lambda api: None)
    monkeypatch.setattr(adapter.common, "_post", fake.post)
    control = tmp_path / "controls"
    pilot = adapter.build_plan(study.PILOT, ORG, control, family=study.FAMILY)
    receipt = adapter.launch(pilot, exact_projections[1][study.PILOT][0], fake)
    fake.status = "Completed."
    assert adapter.poll_status(pilot, receipt, fake) == "Completed."
    expected = {
        "candidate_id": study.PILOT, "attempt": 1,
        "project_id": receipt["project_id"], "backtest_id": receipt["backtest_id"],
        "status": "Completed.",
    }
    adapter.common._write(adapter._path(pilot, "read-claim"), expected)
    statistics = _pilot_statistics(row_for(study.PILOT), remx)
    parsed = study.parse_order(pilot, statistics)
    adapter._write_artifact(adapter._path(pilot, "raw-custom"), {
        **expected, "statistics": statistics,
    })
    adapter._write_artifact(adapter._path(pilot, "result"), {
        **expected, **parsed,
        "manifest_sha256": adapter.FROZEN_QCOM_SCORE_FLOOR1_MANIFEST_SHA256,
        "projection_sha256": row_for(study.PILOT)["projection_sha256"],
    })
    assert study.pilot_post_cap_stock_target_counts(parsed) == (remx, total)
    next_arm = adapter.build_plan("R260", ORG, control, family=study.FAMILY)
    if allowed:
        study.require_successful_pilot(next_arm)
    else:
        with pytest.raises(adapter.RelaxedQcSubmissionError, match="did not increase"):
            study.require_successful_pilot(next_arm)


def test_invalid_completed_pilot_does_not_mask_valid_second_attempt(tmp_path, monkeypatch):
    control = tmp_path / "controls"
    monkeypatch.setattr(adapter, "_receipt", lambda plan, launch: {})
    monkeypatch.setattr(study, "parse_order", lambda plan, statistics:
                        _count_only_result(1, 12212) if plan.attempt == 2
                        else {"run_valid": False})
    for attempt, valid in ((1, False), (2, True)):
        pilot = adapter.build_plan(study.PILOT, ORG, control, attempt,
                                   family=study.FAMILY)
        expected = {
            "candidate_id": study.PILOT, "attempt": attempt,
            "project_id": 1001, "backtest_id": f"{attempt:032x}",
            "status": "Completed.",
        }
        adapter.common._write(adapter._path(pilot, "launch"), {
            "project_id": 1001, "backtest_id": expected["backtest_id"],
        })
        adapter.common._write(adapter._path(pilot, "terminal"), expected)
        adapter.common._write(adapter._path(pilot, "read-claim"), expected)
        statistics = {name: "{}" for name in study.STATISTIC_NAMES}
        adapter._write_artifact(adapter._path(pilot, "raw-custom"), {
            **expected, "statistics": statistics,
        })
        adapter._write_artifact(adapter._path(pilot, "result"), {
            **expected,
            **(_count_only_result(1, 12212) if valid else {"run_valid": False}),
            "manifest_sha256": adapter.FROZEN_QCOM_SCORE_FLOOR1_MANIFEST_SHA256,
            "projection_sha256": row_for(study.PILOT)["projection_sha256"],
        })
    next_arm = adapter.build_plan("R260", ORG, control, family=study.FAMILY)
    study.require_successful_pilot(next_arm)


def test_mutating_only_saved_result_counts_cannot_unlock_ladder(
    exact_projections, tmp_path, monkeypatch,
):
    fake = Fake()
    monkeypatch.setattr(adapter, "_require_inputs", lambda plan: None)
    monkeypatch.setattr(adapter.common, "_client", lambda api: None)
    monkeypatch.setattr(adapter.common, "_post", fake.post)
    control = tmp_path / "controls"
    pilot = adapter.build_plan(study.PILOT, ORG, control, family=study.FAMILY)
    receipt = adapter.launch(pilot, exact_projections[1][study.PILOT][0], fake)
    fake.status = "Completed."
    assert adapter.poll_status(pilot, receipt, fake) == "Completed."
    expected = {
        "candidate_id": study.PILOT, "attempt": 1,
        "project_id": receipt["project_id"], "backtest_id": receipt["backtest_id"],
        "status": "Completed.",
    }
    adapter.common._write(adapter._path(pilot, "read-claim"), expected)
    statistics = _pilot_statistics(row_for(study.PILOT), 0)
    parsed = study.parse_order(pilot, statistics)
    assert study.pilot_post_cap_stock_target_counts(parsed) == (0, 12211)
    adapter._write_artifact(adapter._path(pilot, "raw-custom"), {
        **expected, "statistics": statistics,
    })
    result_path = adapter._path(pilot, "result")
    adapter._write_artifact(result_path, {
        **expected, **parsed,
        "manifest_sha256": adapter.FROZEN_QCOM_SCORE_FLOOR1_MANIFEST_SHA256,
        "projection_sha256": row_for(study.PILOT)["projection_sha256"],
    })
    next_arm = adapter.build_plan("R260", ORG, control, family=study.FAMILY)
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="did not increase"):
        study.require_successful_pilot(next_arm)
    forged = adapter._read_artifact(result_path)
    forged["aggregates"]["sleeve_diagnostics"]["rows"][4][6] = 1
    forged["aggregates"]["sleeve_diagnostics"]["rows"][4][7] = 1
    # The former count-only gate would have accepted these forged counts.
    assert study.pilot_post_cap_stock_target_counts(forged) == (1, 12212)
    result_path.write_bytes(canonical(forged))
    with pytest.raises(adapter.RelaxedQcSubmissionError, match="differs from retained statistics"):
        study.require_successful_pilot(next_arm)


def test_pilot_order_launch_and_one_bounded_result_read(
    exact_projections, tmp_path, monkeypatch,
):
    fake = Fake()
    monkeypatch.setattr(adapter, "_require_inputs", lambda plan: None)
    monkeypatch.setattr(adapter.common, "_client", lambda api: None)
    monkeypatch.setattr(adapter.common, "_post", fake.post)
    row = row_for(study.PILOT)
    plan = adapter.build_plan(study.PILOT, ORG, tmp_path / "controls", family=study.FAMILY)
    receipt = adapter.launch(plan, exact_projections[1][study.PILOT][0], fake)
    assert [endpoint for endpoint, _ in fake.calls].count("backtests/create") == 1
    fake.status = "Completed."
    assert adapter.poll_status(plan, receipt, fake) == "Completed."
    fake.statistics = {**statistics_fixture(row), "Net Profit": "NOT RETAINED"}
    parsed = adapter.read_result_once(plan, receipt, fake)
    assert parsed["run_valid"] is True
    assert "NOT RETAINED" not in repr(parsed)
    assert [endpoint for endpoint, _ in fake.calls].count("backtests/read") == 1
    with pytest.raises(adapter.common.SixUniverseSettlementSubmissionError):
        adapter.read_result_once(plan, receipt, fake)
