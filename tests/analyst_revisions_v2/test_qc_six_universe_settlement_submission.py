"""Isolating tests for the separately versioned settlement-cash reader."""

import dataclasses
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_delta_order_package as delta
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_settlement_qc_projection as projector
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_tilt100_qc_projection as tilt100_projector
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_qc_runtime as runtime
from research.analyst_revisions_v2_qc import six_universe_cap90_submission as cap90
from research.analyst_revisions_v2_qc import six_universe_settlement_submission as subject
from tests.analyst_revisions_v2 import test_qc_six_universe_tilt_submission as prior_tests
from tests.analyst_revisions_v2 import test_qc_six_universe_tilt40_submission as r185_tests


PACKAGE_PATH = Path(
    "artifacts/analyst_revisions_v2/accepted_risk_delta_order_package_20260918_01/"
    "arv2-preliminary-qc-package-7803b84f0841f9685a4951de"
)


@pytest.fixture(scope="module")
def projections():
    if not PACKAGE_PATH.is_dir():
        pytest.skip("local gitignored ARV2 delta package is unavailable")
    package = delta.load_accepted_risk_delta_order_package(
        PACKAGE_PATH,
        expected_package_sha256=delta.EXPECTED_DELTA_PACKAGE_SHA256,
        expected_lineage_sha256=delta.EXPECTED_DELTA_LINEAGE_SHA256,
    )
    return {
        "R191": projector.build_settlement_projection(package, "R191"),
        "R192": projector.build_settlement_projection(package, "R192"),
        "R193": tilt100_projector.build_tilt100_settlement_projection(package),
    }


def _plan(tmp_path, projection, candidate_id):
    return subject.SettlementQcPlan(
        candidate_id=candidate_id, organization_id="a" * 32,
        package_sha256=projection.package_sha256,
        activation_manifest_sha256=projection.activation_manifest_sha256,
        control_directory=tmp_path / "control",
    )


def _predecessors(monkeypatch, plan):
    r185_tests._predecessors(monkeypatch, plan)


def _fake_qc(monkeypatch, plan, projection, **kwargs):
    monkeypatch.setattr(r185_tests, "subject", subject)
    return r185_tests._fake_qc(monkeypatch, plan, projection, **kwargs)


def _statistics(plan, launch, *, defect=None):
    values = r185_tests._statistics(plan, launch, fraction="0.40")
    aggregate = json.loads(values[runtime.AGGREGATES_STATISTIC_NAME])
    aggregate.pop("order_event_cash_nonnegative")
    aggregate.update({
        "schema": subject._CANDIDATES[plan.candidate_id].summary_schema,
        "role": plan.role,
        "minimum_observed_order_event_cash": "-25",
        "transient_negative_order_event_count": 1,
        "unexplained_negative_order_event_count": 0,
        "negative_cash_requires_pending_sell_moo": True,
        "settled_cash_nonnegative": True,
    })
    aggregate["execution"].update({
        "submitted_rebalance_count": runtime.EXPECTED_DECISION_COUNT,
        "completed_rebalance_count": runtime.EXPECTED_DECISION_COUNT,
        "submitted_order_count": runtime.EXPECTED_DECISION_COUNT,
        "filled_order_count_sum": runtime.EXPECTED_DECISION_COUNT,
        "execution_failure": False,
    })
    if plan.candidate_id == "R191":
        for key in subject._TILT_FIELDS:
            aggregate.pop(key)
    else:
        aggregate.update({
            "matched_baseline_profile_sha256": subject._CANDIDATES["R191"].profile_sha256,
            "matched_baseline_target_path_sha256": subject._PREDECESSOR_TARGET_PATH_SHA256,
            "maximum_stock_weight_change_fraction": subject._TILT_FRACTIONS[plan.candidate_id],
        })
    if defect == "digest":
        pass
    elif defect == "unknown":
        aggregate["unexpected"] = True
    elif defect == "unexplained":
        aggregate["unexplained_negative_order_event_count"] = 1
    raw = subject._canonical(aggregate)
    meta = json.loads(values[runtime.META_STATISTIC_NAME])
    meta.update({
        "role": plan.role,
        "aggregate_schema": aggregate["schema"],
        "aggregate_sha256": "0" * 64 if defect == "digest" else hashlib.sha256(raw).hexdigest(),
    })
    return {
        runtime.META_STATISTIC_NAME: subject._canonical(meta).decode("ascii"),
        runtime.AGGREGATES_STATISTIC_NAME: raw.decode("ascii"),
        "Net Profit": "999%",  # Standard QC statistics must not be retained.
    }


def _aggregate(candidate_id="R192"):
    plan = SimpleNamespace(
        role="matched_revision_tilt80", profile_sha256="a" * 64,
        package_sha256="b" * 64, activation_manifest_sha256="c" * 64,
    )
    legacy = prior_tests._statistics(plan, {"profile_id": "profile"})
    aggregate = json.loads(legacy[runtime.AGGREGATES_STATISTIC_NAME])
    aggregate.pop("order_event_cash_nonnegative")
    aggregate.update({
        "schema": "settlement-summary",
        "role": ("matched" if candidate_id == "R191" else
                 f"matched_revision_tilt{80 if candidate_id == 'R192' else 100}"),
        "minimum_observed_order_event_cash": "-25",
        "transient_negative_order_event_count": 1,
        "unexplained_negative_order_event_count": 0,
        "negative_cash_requires_pending_sell_moo": True,
        "settled_cash_nonnegative": True,
    })
    aggregate["execution"].update({
        "submitted_rebalance_count": runtime.EXPECTED_DECISION_COUNT,
        "completed_rebalance_count": runtime.EXPECTED_DECISION_COUNT,
        "submitted_order_count": runtime.EXPECTED_DECISION_COUNT,
        "filled_order_count_sum": runtime.EXPECTED_DECISION_COUNT,
        "execution_failure": False,
    })
    if candidate_id in subject._TILT_FRACTIONS:
        aggregate.update({
            "matched_baseline_profile_sha256": subject._MATCHED_SETTLEMENT_PROFILE_SHA256,
            "matched_baseline_target_path_sha256": subject._PREDECESSOR_TARGET_PATH_SHA256,
            "maximum_stock_weight_change_fraction": subject._TILT_FRACTIONS[candidate_id],
        })
    else:
        for key in subject._TILT_FIELDS:
            aggregate.pop(key)
    candidate = subject._Candidate(
        candidate_id, "private", aggregate["role"], "settlement-variant",
        "settlement-projection", "a" * 64, "a" * 64, "a" * 64,
        16 if candidate_id in subject._TILT_FRACTIONS else 14, 400_000,
        "settlement-summary", "owner-waiver",
    )
    return aggregate, candidate


@pytest.mark.parametrize("candidate_id", ("R191", "R192", "R193"))
def test_signed_temporary_cash_is_retained_without_old_nonnegative_claim(candidate_id):
    aggregate, candidate = _aggregate(candidate_id)
    selected = subject._settlement_aggregate(
        aggregate, candidate,
        matched_target_path=subject._PREDECESSOR_TARGET_PATH_SHA256,
    )
    assert selected["minimum_observed_order_event_cash"] == "-25"
    assert selected["transient_negative_order_event_count"] == 1
    assert "order_event_cash_nonnegative" not in selected
    assert selected["run_valid"] is True


@pytest.mark.parametrize("defect", (
    "unknown_field", "old_claim", "nonfinite", "negative_daily", "missing_pending_sell",
    "unexplained", "settled_negative", "inconsistent_negative_count", "gross",
    "tracking", "invalid_order", "canceled_order", "unfilled_order",
    "missing_rebalance", "wrong_tilt", "wrong_baseline", "old_baseline",
))
def test_new_reader_isolates_every_cash_and_order_gate(defect):
    aggregate, candidate = _aggregate()
    if defect == "unknown_field":
        aggregate["unexpected"] = 1
    elif defect == "old_claim":
        aggregate["order_event_cash_nonnegative"] = True
    elif defect == "nonfinite":
        aggregate["minimum_observed_order_event_cash"] = "NaN"
    elif defect == "negative_daily":
        aggregate["minimum_end_day_cash"] = "-1"
    elif defect == "missing_pending_sell":
        aggregate["negative_cash_requires_pending_sell_moo"] = False
    elif defect == "unexplained":
        aggregate["unexplained_negative_order_event_count"] = 1
    elif defect == "settled_negative":
        aggregate["settled_cash_nonnegative"] = False
    elif defect == "inconsistent_negative_count":
        aggregate["transient_negative_order_event_count"] = 0
    elif defect == "gross":
        aggregate["maximum_gross_exposure"] = "1.01"
    elif defect == "tracking":
        aggregate["execution"]["maximum_target_weight_l1_error"] = "0.06"
    elif defect == "invalid_order":
        aggregate["execution"]["invalid_order_count_sum"] = 1
    elif defect == "canceled_order":
        aggregate["execution"]["canceled_order_count_sum"] = 1
    elif defect == "unfilled_order":
        aggregate["execution"]["filled_order_count_sum"] -= 1
    elif defect == "missing_rebalance":
        aggregate["execution"]["completed_rebalance_count"] -= 1
    elif defect == "wrong_tilt":
        aggregate["maximum_stock_weight_change_fraction"] = "0.40"
    elif defect == "wrong_baseline":
        aggregate["matched_baseline_profile_sha256"] = "0" * 64
    elif defect == "old_baseline":
        aggregate["matched_baseline_profile_sha256"] = cap90._R182_BRIDGE_PROFILE_SHA256
    with pytest.raises(subject.SixUniverseSettlementSubmissionError):
        subject._settlement_aggregate(
            aggregate, candidate,
            matched_target_path=subject._PREDECESSOR_TARGET_PATH_SHA256,
        )


@pytest.mark.parametrize("candidate_id,source_count", (
    ("R191", 14), ("R192", 16), ("R193", 16),
))
def test_exact_preview_and_candidate_specific_owner_waiver(
    projections, tmp_path, monkeypatch, candidate_id, source_count,
):
    projection = projections[candidate_id]
    plan = _plan(tmp_path, projection, candidate_id)
    identity = subject.preview(plan, projection)
    assert len(identity["source_files"]) == source_count
    expected_sha = (tilt100_projector.PINNED_TILT100_PROJECTION_SHA256
                    if candidate_id == "R193" else
                    projector.CANDIDATES[candidate_id]["projection_sha256"])
    assert identity["projection_sha256"] == expected_sha
    _predecessors(monkeypatch, plan)
    waiver = json.loads(subject.render_owner_waiver_payload(plan, projection))
    assert waiver["candidate_id"] == candidate_id
    assert waiver["owner_launch_waiver_id"] == subject._CANDIDATES[candidate_id].waiver_id
    assert waiver["source_files_sha256"] == subject._CANDIDATES[candidate_id].source_files_sha256
    assert waiver["maximum_backtest_submissions"] == 1
    assert waiver["maximum_result_reads"] == 1
    assert waiver["raw_logs_orders_charts_authorized"] is False
    if candidate_id == "R193":
        assert waiver["project_name"] == (
            "115 ARV2 SIX CAP90 SETTLED TILT100 R193 2021 2025"
        )
        assert waiver["backtest_name"] == (
            "ARV2 R193A1 six cap90 settlement 2021 2025 473163be"
        )
        assert waiver["owner_launch_waiver_id"] == (
            "ARV2-OWNER-2026-09-25-R193A1-TILT100-SETTLEMENT-"
            "EXPLORATORY-SIGNATURE-WAIVER"
        )


@pytest.mark.parametrize("candidate_id", ("R191", "R192", "R193"))
def test_wrong_waiver_or_source_refuses_before_qc(
    projections, tmp_path, monkeypatch, candidate_id,
):
    projection = projections[candidate_id]
    plan = _plan(tmp_path, projection, candidate_id)
    _predecessors(monkeypatch, plan)
    calls, _ = _fake_qc(monkeypatch, plan, projection)
    with pytest.raises(subject.SixUniverseSettlementSubmissionError, match="waiver"):
        subject.launch_a1(plan, projection, object(), owner_waiver_id="wrong")
    item = projection.source_files[0]
    changed = item.source_bytes + b"# changed\n"
    files = list(projection.source_files)
    files[0] = dataclasses.replace(
        item, source_bytes=changed, byte_count=len(changed),
        content_sha256=hashlib.sha256(changed).hexdigest(),
    )
    altered = dataclasses.replace(
        projection, source_files=tuple(files),
        total_source_byte_count=projection.total_source_byte_count + len(b"# changed\n"),
    )
    with pytest.raises(subject.SixUniverseSettlementSubmissionError):
        subject.launch_a1(
            plan, altered, object(),
            owner_waiver_id=subject._CANDIDATES[candidate_id].waiver_id,
        )
    assert calls == []
    assert not subject._control_path(plan, "claim").exists()


@pytest.mark.parametrize("candidate_id", ("R191", "R192", "R193"))
def test_a1_launch_status_and_one_signed_cash_aggregate_read(
    projections, tmp_path, monkeypatch, candidate_id,
):
    projection = projections[candidate_id]
    plan = _plan(tmp_path, projection, candidate_id)
    _predecessors(monkeypatch, plan)
    calls, state = _fake_qc(monkeypatch, plan, projection)
    launch = subject.launch_a1(
        plan, projection, object(),
        owner_waiver_id=subject._CANDIDATES[candidate_id].waiver_id,
    )
    assert calls.count("backtests/create") == 1
    assert subject.poll_status(plan, launch, object()) == "Completed."
    state["statistics"] = _statistics(plan, launch)
    before = len(calls)
    result = subject.read_aggregates_once(plan, launch, object())
    assert result["run_valid"] is True
    assert result["aggregates"]["minimum_observed_order_event_cash"] == "-25"
    assert "order_event_cash_nonnegative" not in result["aggregates"]
    assert calls[before:] == ["files/read", "backtests/read"]
    assert subject._control_path(plan, "result-valid").exists()
    with pytest.raises(subject.SixUniverseSettlementSubmissionError,
                       match="already claimed"):
        subject.read_aggregates_once(plan, launch, object())
    with pytest.raises(subject.SixUniverseSettlementSubmissionError,
                       match="already claimed"):
        subject.launch_a1(
            plan, projection, object(),
            owner_waiver_id=subject._CANDIDATES[candidate_id].waiver_id,
        )


@pytest.mark.parametrize("candidate_id", ("R191", "R192", "R193"))
@pytest.mark.parametrize("defect", ("digest", "unknown", "unexplained"))
def test_one_result_read_refuses_changed_digest_or_cash_policy(
    projections, tmp_path, monkeypatch, candidate_id, defect,
):
    projection = projections[candidate_id]
    plan = _plan(tmp_path, projection, candidate_id)
    _predecessors(monkeypatch, plan)
    calls, state = _fake_qc(monkeypatch, plan, projection)
    launch = subject.launch_a1(
        plan, projection, object(),
        owner_waiver_id=subject._CANDIDATES[candidate_id].waiver_id,
    )
    assert subject.poll_status(plan, launch, object()) == "Completed."
    state["statistics"] = _statistics(plan, launch, defect=defect)
    before = len(calls)
    with pytest.raises(subject.SixUniverseSettlementSubmissionError):
        subject.read_aggregates_once(plan, launch, object())
    assert calls[before:] == ["files/read", "backtests/read"]
    assert subject._control_path(plan, "result-read-claim").exists()
    assert not subject._control_path(plan, "result-valid").exists()


def test_r193_result_refuses_r192_fraction_even_with_correct_settlement_policy():
    aggregate, candidate = _aggregate("R193")
    aggregate["maximum_stock_weight_change_fraction"] = "0.80"
    with pytest.raises(subject.SixUniverseSettlementSubmissionError,
                       match="tilt or matched target"):
        subject._settlement_aggregate(
            aggregate, candidate,
            matched_target_path=subject._PREDECESSOR_TARGET_PATH_SHA256,
        )
