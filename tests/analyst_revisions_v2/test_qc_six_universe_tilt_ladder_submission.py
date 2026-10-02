"""Focused exact launch/result controls for the three tilt sensitivities."""

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from research.analyst_revisions_v2_qc import accepted_risk_delta_order_package as delta
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_qc_runtime as runtime
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_tilt_ladder_qc_projection as projector
from research.analyst_revisions_v2_qc import six_universe_tilt_ladder_submission as subject
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
    return {percent: projector.build_tilt_ladder_projection(package, percent)
            for percent in projector.PERCENTS}


def _plan(tmp_path, projection, percent):
    return subject.TiltLadderQcPlan(
        percent=percent,
        organization_id="a" * 32,
        package_sha256=projection.package_sha256,
        activation_manifest_sha256=projection.activation_manifest_sha256,
        control_directory=tmp_path / "control",
    )


def _predecessors(monkeypatch, plan, *, target_path=r185_tests.TARGET_PATH_SHA256):
    # This creates actual R182 receipt fixtures. Do not replace the ladder's
    # predecessor gate: exercise its R186 -> R184 -> R182 delegation.
    r185_tests._predecessors(monkeypatch, plan, target_path=target_path)


def _fake_qc(monkeypatch, plan, projection, **kwargs):
    # Reuse the unchanged QC envelope, but route its `_post` seam to this
    # launcher. None of this candidate's preview/launch/read logic is patched.
    monkeypatch.setattr(r185_tests, "subject", subject)
    return r185_tests._fake_qc(monkeypatch, plan, projection, **kwargs)


def _statistics(plan, launch, *, fraction=None, defect=None):
    values = r185_tests._statistics(plan, launch)
    aggregate = json.loads(values[runtime.AGGREGATES_STATISTIC_NAME])
    aggregate["schema"] = (
        f"arv2-six-universe-order-tilt{plan.percent}-bridge-summary-v1"
    )
    aggregate["maximum_stock_weight_change_fraction"] = (
        fraction if fraction is not None else f"0.{plan.percent:02d}"
    )
    if defect == "negative_cash":
        aggregate["minimum_end_day_cash"] = "-1"
    elif defect == "invalid_order":
        aggregate["execution"]["invalid_order_count_sum"] = 1
    raw = subject._canonical(aggregate)
    meta = json.loads(values[runtime.META_STATISTIC_NAME])
    meta["aggregate_schema"] = aggregate["schema"]
    meta["aggregate_sha256"] = hashlib.sha256(raw).hexdigest()
    return {
        runtime.META_STATISTIC_NAME: subject._canonical(meta).decode("ascii"),
        runtime.AGGREGATES_STATISTIC_NAME: raw.decode("ascii"),
        "Net Profit": "999%",  # Standard QC statistics are never retained.
    }


@pytest.mark.parametrize("percent,candidate_id,project_number", (
    (70, "R187", "110"), (60, "R188", "111"), (50, "R189", "112"),
))
def test_exact_preview_and_waiver_bind_each_candidate(
    projections, tmp_path, monkeypatch, percent, candidate_id, project_number,
):
    projection = projections[percent]
    plan = _plan(tmp_path, projection, percent)
    identity = subject.preview(plan, projection)
    assert identity["candidate_id"] == candidate_id
    assert identity["attempt"] == 1
    assert len(identity["source_files"]) == 16
    assert identity["projection_sha256"] == projector.PINNED_PROJECTIONS[percent]
    _predecessors(monkeypatch, plan)
    waiver = json.loads(subject.render_owner_waiver_payload(plan, projection))
    assert waiver["candidate_id"] == candidate_id
    assert waiver["tilt_percent"] == percent
    assert waiver["project_name"].startswith(project_number + " ")
    assert waiver["source_files_sha256"] == subject._CANDIDATES[percent].source_files_sha256
    assert waiver["matched_baseline_target_path_sha256"] == r185_tests.TARGET_PATH_SHA256
    assert waiver["owner_launch_waiver_id"] == subject._CANDIDATES[percent].waiver_id
    assert waiver["maximum_backtest_submissions"] == 1
    assert waiver["maximum_result_reads"] == 1
    assert waiver["raw_logs_orders_charts_authorized"] is False
    assert waiver["paper_live_deployment_funded_trading_authorized"] is False


@pytest.mark.parametrize("percent", (70, 60, 50))
def test_valid_predecessor_gate_and_changed_digest_refusal(
    projections, tmp_path, monkeypatch, percent,
):
    plan = _plan(tmp_path, projections[percent], percent)
    _predecessors(monkeypatch, plan)
    assert subject._require_valid_predecessors(plan) == r185_tests.TARGET_PATH_SHA256
    # A structurally well-formed but different R182 target path is not enough.
    wrong = dataclasses.replace(plan, control_directory=tmp_path / "wrong")
    _predecessors(monkeypatch, wrong, target_path="f" * 64)
    with pytest.raises(subject.SixUniverseTiltLadderSubmissionError,
                       match="preregistered pin"):
        subject._require_valid_predecessors(wrong)


@pytest.mark.parametrize("percent", (70, 60, 50))
def test_wrong_waiver_or_changed_source_refuses_before_qc(
    projections, tmp_path, monkeypatch, percent,
):
    projection = projections[percent]
    plan = _plan(tmp_path, projection, percent)
    _predecessors(monkeypatch, plan)
    calls, _state = _fake_qc(monkeypatch, plan, projection)
    wrong_percent = 60 if percent == 70 else 70
    with pytest.raises(subject.SixUniverseTiltLadderSubmissionError, match="waiver"):
        subject.launch_a1(
            plan, projection, object(),
            owner_waiver_id=subject._CANDIDATES[wrong_percent].waiver_id,
        )
    item = projection.source_files[0]
    raw = item.source_bytes + b"# altered\n"
    files = list(projection.source_files)
    files[0] = dataclasses.replace(
        item, source_bytes=raw, byte_count=len(raw),
        content_sha256=hashlib.sha256(raw).hexdigest(),
    )
    altered = dataclasses.replace(
        projection, source_files=tuple(files),
        total_source_byte_count=projection.total_source_byte_count + len(b"# altered\n"),
    )
    with pytest.raises(subject.SixUniverseTiltLadderSubmissionError):
        subject.launch_a1(
            plan, altered, object(),
            owner_waiver_id=subject._CANDIDATES[percent].waiver_id,
        )
    assert calls == []
    assert not subject._control_path(plan, "claim").exists()


@pytest.mark.parametrize("percent", (70, 60, 50))
def test_a1_launch_status_and_one_aggregate_read(
    projections, tmp_path, monkeypatch, percent,
):
    projection = projections[percent]
    plan = _plan(tmp_path, projection, percent)
    _predecessors(monkeypatch, plan)
    calls, state = _fake_qc(monkeypatch, plan, projection)
    launch = subject.launch_a1(
        plan, projection, object(),
        owner_waiver_id=subject._CANDIDATES[percent].waiver_id,
    )
    assert calls.count("backtests/create") == 1
    assert launch["owner_launch_waiver_id"] == subject._CANDIDATES[percent].waiver_id
    assert subject.poll_status(plan, launch, object()) == "Completed."
    state["statistics"] = _statistics(plan, launch)
    before = len(calls)
    result = subject.read_aggregates_once(plan, launch, object())
    assert result["run_valid"] is True
    assert result["aggregates"]["maximum_stock_weight_change_fraction"] == f"0.{percent:02d}"
    assert calls[before:] == ["files/read", "backtests/read"]
    assert subject._control_path(plan, "result-valid").exists()
    with pytest.raises(subject.SixUniverseTiltLadderSubmissionError,
                       match="already claimed"):
        subject.read_aggregates_once(plan, launch, object())
    with pytest.raises(subject.SixUniverseTiltLadderSubmissionError,
                       match="already claimed"):
        subject.launch_a1(
            plan, projection, object(),
            owner_waiver_id=subject._CANDIDATES[percent].waiver_id,
        )


@pytest.mark.parametrize("percent", (70, 60, 50))
@pytest.mark.parametrize("defect", ("fraction", "negative_cash", "invalid_order"))
def test_aggregate_read_refuses_wrong_weight_or_invalid_account(
    projections, tmp_path, monkeypatch, percent, defect,
):
    projection = projections[percent]
    plan = _plan(tmp_path, projection, percent)
    _predecessors(monkeypatch, plan)
    calls, state = _fake_qc(monkeypatch, plan, projection)
    launch = subject.launch_a1(
        plan, projection, object(),
        owner_waiver_id=subject._CANDIDATES[percent].waiver_id,
    )
    assert subject.poll_status(plan, launch, object()) == "Completed."
    state["statistics"] = _statistics(
        plan, launch,
        fraction="0.99" if defect == "fraction" else None,
        defect=defect,
    )
    before = len(calls)
    with pytest.raises(subject.SixUniverseTiltLadderSubmissionError):
        subject.read_aggregates_once(plan, launch, object())
    assert calls[before:] == ["files/read", "backtests/read"]
    assert not subject._control_path(plan, "result-valid").exists()


def test_candidate_controls_are_separate(projections, tmp_path, monkeypatch):
    plans = {percent: _plan(tmp_path, projections[percent], percent)
             for percent in projector.PERCENTS}
    paths = {percent: subject._control_path(plan, "claim")
             for percent, plan in plans.items()}
    assert len(set(paths.values())) == 3
    assert {path.name for path in paths.values()} == {
        "R187-A1-claim.json", "R188-A1-claim.json", "R189-A1-claim.json",
    }


def test_compile_failure_spends_a1_without_backtest_launch(
    projections, tmp_path, monkeypatch,
):
    projection = projections[70]
    plan = _plan(tmp_path, projection, 70)
    _predecessors(monkeypatch, plan)
    calls, _state = _fake_qc(monkeypatch, plan, projection, compile_error=True)
    with pytest.raises(subject.SixUniverseTiltLadderSubmissionError,
                       match="compile failed"):
        subject.launch_a1(
            plan, projection, object(),
            owner_waiver_id=subject._CANDIDATES[70].waiver_id,
        )
    assert calls.count("compile/create") == 1
    assert "backtests/create" not in calls
    assert subject._control_path(plan, "claim").exists()
    with pytest.raises(subject.SixUniverseTiltLadderSubmissionError,
                       match="already claimed"):
        subject.launch_a1(
            plan, projection, object(),
            owner_waiver_id=subject._CANDIDATES[70].waiver_id,
        )


def test_tampered_waiver_receipts_refuse_before_result_network_read(
    projections, tmp_path, monkeypatch,
):
    projection = projections[60]
    plan = _plan(tmp_path, projection, 60)
    _predecessors(monkeypatch, plan)
    calls, state = _fake_qc(monkeypatch, plan, projection)
    launch = subject.launch_a1(
        plan, projection, object(),
        owner_waiver_id=subject._CANDIDATES[60].waiver_id,
    )
    assert subject.poll_status(plan, launch, object()) == "Completed."
    state["statistics"] = _statistics(plan, launch)
    claim_path = subject._control_path(plan, "claim")
    launch_path = subject._control_path(plan, "launch")
    claim = subject._read(claim_path)
    altered_launch = dict(launch)
    claim["owner_waived_payload_sha256"] = "f" * 64
    altered_launch["owner_waived_payload_sha256"] = "f" * 64
    claim_path.write_bytes(subject._canonical(claim))
    launch_path.write_bytes(subject._canonical(altered_launch))
    before = len(calls)
    with pytest.raises(subject.SixUniverseTiltLadderSubmissionError,
                       match="waiver receipt"):
        subject.read_aggregates_once(plan, altered_launch, object())
    assert calls[before:] == []
    assert not subject._control_path(plan, "result-read-claim").exists()
