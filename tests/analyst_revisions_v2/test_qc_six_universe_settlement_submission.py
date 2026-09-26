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
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_tilt100_floor_qc_projection as floor_projector
from research.analyst_revisions_v2_qc import accepted_risk_six_universe_order_tilt_ladder_floor_qc_projection as ladder_projector
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
        "R194": floor_projector.build_tilt100_floor_projection(package),
        "R195": ladder_projector.build_tilt_floor_projection(package, 100),
        "R196": ladder_projector.build_tilt_floor_projection(package, 120),
        "R197": ladder_projector.build_tilt_floor_projection(package, 140),
        "R198": ladder_projector.build_tilt_floor_projection(package, 160),
        "R199": ladder_projector.build_tilt_floor_projection(package, 180),
        "R200": ladder_projector.build_tilt_floor_projection(package, 200),
        "R201": ladder_projector.build_tilt_floor_projection(package, 250),
        "R202": ladder_projector.build_tilt_floor_projection(package, 300),
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


def _statistics(plan, launch, *, defect=None,
                target_path=subject._PREDECESSOR_TARGET_PATH_SHA256):
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
            "matched_baseline_target_path_sha256": target_path,
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
                 floor_projector.TILT_ROLE if candidate_id == "R194" else
                 ladder_projector.TILT_ROLES[subject._LADDER_PERCENTS[candidate_id]]
                 if candidate_id in subject._LADDER_PERCENTS else
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


@pytest.mark.parametrize("candidate_id", (
    "R191", "R192", "R193", "R194", "R195", "R196", "R197", "R198", "R199", "R200",
    "R201", "R202",
))
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
    ("R191", 14), ("R192", 16), ("R193", 16), ("R194", 16),
))
def test_exact_preview_and_candidate_specific_owner_waiver(
    projections, tmp_path, monkeypatch, candidate_id, source_count,
):
    projection = projections[candidate_id]
    plan = _plan(tmp_path, projection, candidate_id)
    identity = subject.preview(plan, projection)
    assert len(identity["source_files"]) == source_count
    expected_sha = (floor_projector.PINNED_PROJECTION_SHA256
                    if candidate_id == "R194" else
                    tilt100_projector.PINNED_TILT100_PROJECTION_SHA256
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
    if candidate_id == "R194":
        assert identity["r193_lineage_look_number"] == 4
        assert identity["owner_one_time_exception"] is True
        assert waiver["r193_lineage_look_number"] == 4
        assert waiver["r193_prior_looks_spent"] == 3
        assert waiver["maximum_additional_r193_lineage_submissions"] == 1
        assert waiver["owner_one_time_exception"] is True
    else:
        assert "r193_lineage_look_number" not in waiver
        assert "owner_one_time_exception" not in waiver
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


@pytest.mark.parametrize("candidate_id", (
    "R191", "R192", "R193", "R194", "R195", "R196", "R197", "R198", "R199", "R200",
    "R201", "R202",
))
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


@pytest.mark.parametrize("candidate_id", (
    "R191", "R192", "R193", "R194", "R195", "R196", "R197", "R198", "R199", "R200",
    "R201", "R202",
))
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
    if candidate_id in subject._LADDER_PERCENTS:
        assert result["comparison_valid"] is False
        receipt = subject._read(subject._control_path(plan, "result-valid"))
        assert receipt["matched_baseline_target_path_sha256"] == (
            subject._PREDECESSOR_TARGET_PATH_SHA256
        )
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


@pytest.mark.parametrize("candidate_id", (
    "R191", "R192", "R193", "R194", "R195", "R196", "R197", "R198", "R199", "R200",
    "R201", "R202",
))
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


def test_prior_waiver_payload_digests_are_unchanged():
    """The new ladder cannot alter any earlier authority payload bytes."""
    pinned = {
        "R191": "39e86b9b9f7cea0d2b4563505deeaec95ae106ed1810c8883ac1608e645c5738",
        "R192": "6207b84a3985c1693769d8a25e36853f005e0acfe65fdb6235787263cb812dee",
        "R193": "e11e77fe3e1be42df75291d84886d74d4a8dec7e12128c0a464f5cb5c54d19af",
        "R194": "d2e0ba03bf63ecfc409586d1314015870dacbff6bcb16fd25257abd52f1e28ad",
        "R195": "c3897251d66f14f5a0c0d46ef783b34f3d12413aff9c1b34fa0cc256dfe2cb86",
        "R196": "8d20fa19c5e0204815d3886f4834ecd4ab01c47f24c078b64417dc3f004da19f",
        "R197": "8110689f1ba355ef86b7dac73254ce3d489513c943dd9e3fcbf76914c79a4805",
    }
    for candidate_id, expected in pinned.items():
        plan = subject.SettlementQcPlan(
            candidate_id, "a" * 32, "b" * 64, "c" * 64,
            Path("/tmp/arv2-settlement-waiver-pin"),
        )
        actual = hashlib.sha256(subject._waiver_payload(
            plan, {"profile_id": "p"},
            None if candidate_id in subject._LADDER_PERCENTS
            else subject._PREDECESSOR_TARGET_PATH_SHA256,
        )).hexdigest()
        assert actual == expected


def test_r194_claim_and_result_refuse_tampered_lineage(
    projections, tmp_path, monkeypatch,
):
    projection = projections["R194"]
    plan = _plan(tmp_path, projection, "R194")
    _predecessors(monkeypatch, plan)
    calls, state = _fake_qc(monkeypatch, plan, projection)
    launch = subject.launch_a1(
        plan, projection, object(),
        owner_waiver_id=subject._CANDIDATES["R194"].waiver_id,
    )
    assert calls.count("backtests/create") == 1
    assert launch["r193_lineage_look_number"] == 4
    assert launch["owner_one_time_exception"] is True
    assert subject.poll_status(plan, launch, object()) == "Completed."
    state["statistics"] = _statistics(plan, launch)
    tampered = dict(launch, r193_lineage_look_number=1)
    before = len(calls)
    with pytest.raises(subject.SixUniverseSettlementSubmissionError,
                       match="fourth R193-lineage look"):
        subject.read_aggregates_once(plan, tampered, object())
    assert calls[before:] == []
    assert not subject._control_path(plan, "result-read-claim").exists()
    claim_path = subject._control_path(plan, "claim")
    claim = json.loads(claim_path.read_text())
    claim["owner_one_time_exception"] = False
    monkeypatch.setattr(subject, "_read", lambda path: (
        claim if path == claim_path else cap90._read_control(path)
    ))
    before = len(calls)
    with pytest.raises(subject.SixUniverseSettlementSubmissionError,
                       match="one-time fourth lineage look"):
        subject.read_aggregates_once(plan, launch, object())
    assert calls[before:] == []
    assert not subject._control_path(plan, "result-read-claim").exists()


def test_r194_profile_floor_mutation_refuses_before_qc(
    projections, tmp_path, monkeypatch,
):
    projection = projections["R194"]
    plan = _plan(tmp_path, projection, "R194")
    profile = floor_projector.require_tilt100_floor_profile()
    monkeypatch.setattr(subject.floor_projection, "require_tilt100_floor_profile",
                        lambda: dict(profile, minimum_stock_residual_weight="0"))
    with pytest.raises(subject.SixUniverseSettlementSubmissionError,
                       match="positive-residual"):
        subject.launch_a1(plan, projection, object(),
                          owner_waiver_id=subject._CANDIDATES["R194"].waiver_id)
    assert not subject._control_path(plan, "claim").exists()


@pytest.mark.parametrize("candidate_id,percent", (
    ("R195", 100), ("R196", 120), ("R197", 140),
    ("R198", 160), ("R199", 180), ("R200", 200),
    ("R201", 250), ("R202", 300),
))
def test_guarded_ladder_preview_and_owner_waiver(
    projections, tmp_path, monkeypatch, candidate_id, percent,
):
    projection = projections[candidate_id]
    plan = _plan(tmp_path, projection, candidate_id)
    identity = subject.preview(plan, projection)
    assert identity["projection_sha256"] == (
        ladder_projector.PINNED_PROJECTION_SHA256S[percent]
    )
    assert identity["profile_sha256"] == (
        ladder_projector.PINNED_PROFILE_SHA256S[percent]
    )
    assert len(identity["source_files"]) == 16
    _predecessors(monkeypatch, plan)
    waiver = json.loads(subject.render_owner_waiver_payload(plan, projection))
    assert waiver["matched_baseline_target_path_sha256"] is None
    assert waiver["historical_r182_target_path_sha256"] == (
        subject._PREDECESSOR_TARGET_PATH_SHA256
    )
    assert waiver["matched_target_path_policy_id"] == (
        "producer_derived_per_candidate_v1"
    )
    assert waiver["comparison_requires_valid_r195_exact_path"] is True
    assert waiver["project_name"].startswith({
        100: "117 ", 120: "118 ", 140: "119 ",
        160: "120 ", 180: "121 ", 200: "122 ",
        250: "123 ", 300: "124 ",
    }[percent])
    assert waiver["source_files_sha256"] == (
        ladder_projector.PINNED_SOURCE_MANIFEST_SHA256S[percent]
    )
    if candidate_id == "R195":
        assert identity["r193_lineage_look_number"] == 5
        assert waiver["r193_lineage_look_number"] == 5
        assert waiver["r193_prior_looks_spent"] == 4
        assert waiver["owner_explicit_additional_look"] is True
    else:
        assert "r193_lineage_look_number" not in waiver


@pytest.mark.parametrize("candidate_id", (
    "R195", "R196", "R197", "R198", "R199", "R200",
    "R201", "R202",
))
@pytest.mark.parametrize("bad_path", (None, "F" * 64, "bad"))
def test_guarded_ladder_refuses_malformed_producer_path(candidate_id, bad_path):
    aggregate, candidate = _aggregate(candidate_id)
    aggregate["matched_baseline_target_path_sha256"] = bad_path
    with pytest.raises(subject.SixUniverseSettlementSubmissionError,
                       match="producer-derived matched target path"):
        subject._settlement_aggregate(
            aggregate, candidate, matched_target_path=None,
        )


@pytest.mark.parametrize("candidate_id,wrong_fraction", (
    ("R198", "1.40"), ("R199", "1.60"), ("R200", "1.80"),
    ("R201", "2.00"), ("R202", "2.50"),
))
def test_extended_ladder_result_refuses_neighboring_candidate_fraction(
    candidate_id, wrong_fraction,
):
    aggregate, candidate = _aggregate(candidate_id)
    aggregate["maximum_stock_weight_change_fraction"] = wrong_fraction
    with pytest.raises(subject.SixUniverseSettlementSubmissionError,
                       match="tilt or matched target"):
        subject._settlement_aggregate(
            aggregate, candidate, matched_target_path=None,
        )


@pytest.mark.parametrize("candidate_id", (
    "R196", "R197", "R198", "R199", "R200",
    "R201", "R202",
))
@pytest.mark.parametrize("same_path", (True, False))
def test_guarded_ladder_comparison_needs_valid_r195_same_path(
    projections, tmp_path, monkeypatch, candidate_id, same_path,
):
    anchor_path = "d" * 64
    r195_projection = projections["R195"]
    r195_plan = _plan(tmp_path, r195_projection, "R195")
    _predecessors(monkeypatch, r195_plan)
    _, r195_qc = _fake_qc(monkeypatch, r195_plan, r195_projection)
    r195_launch = subject.launch_a1(
        r195_plan, r195_projection, object(),
        owner_waiver_id=subject._CANDIDATES["R195"].waiver_id,
    )
    assert subject.poll_status(r195_plan, r195_launch, object()) == "Completed."
    r195_qc["statistics"] = _statistics(
        r195_plan, r195_launch, target_path=anchor_path,
    )
    r195_result = subject.read_aggregates_once(r195_plan, r195_launch, object())
    assert r195_result["run_valid"] is True
    assert r195_result["comparison_valid"] is False
    r195_receipt = subject._read(subject._control_path(r195_plan, "result-valid"))
    assert r195_receipt["matched_baseline_target_path_sha256"] == anchor_path

    projection = projections[candidate_id]
    plan = _plan(tmp_path, projection, candidate_id)
    _, qc = _fake_qc(monkeypatch, plan, projection)
    launch = subject.launch_a1(
        plan, projection, object(),
        owner_waiver_id=subject._CANDIDATES[candidate_id].waiver_id,
    )
    assert subject.poll_status(plan, launch, object()) == "Completed."
    observed_path = anchor_path if same_path else "e" * 64
    qc["statistics"] = _statistics(
        plan, launch, target_path=observed_path,
    )
    result = subject.read_aggregates_once(plan, launch, object())
    assert result["run_valid"] is True
    assert result["comparison_valid"] is same_path
    receipt = subject._read(subject._control_path(plan, "result-valid"))
    assert receipt["matched_baseline_target_path_sha256"] == observed_path
    assert receipt["comparison_valid"] is same_path


@pytest.mark.parametrize("candidate_id", (
    "R196", "R197", "R198", "R199", "R200",
    "R201", "R202",
))
def test_guarded_ladder_invalid_r195_receipt_cannot_enable_comparison(
    projections, tmp_path, monkeypatch, candidate_id,
):
    anchor_plan = _plan(tmp_path, projections["R195"], "R195")
    _predecessors(monkeypatch, anchor_plan)
    subject._write(subject._control_path(anchor_plan, "result-valid"), {
        "candidate_id": "R195", "run_valid": True,
        "matched_baseline_target_path_sha256": "d" * 64,
    })
    projection = projections[candidate_id]
    plan = _plan(tmp_path, projection, candidate_id)
    _, qc = _fake_qc(monkeypatch, plan, projection)
    launch = subject.launch_a1(
        plan, projection, object(),
        owner_waiver_id=subject._CANDIDATES[candidate_id].waiver_id,
    )
    assert subject.poll_status(plan, launch, object()) == "Completed."
    qc["statistics"] = _statistics(plan, launch, target_path="d" * 64)
    result = subject.read_aggregates_once(plan, launch, object())
    assert result["run_valid"] is True
    assert result["comparison_valid"] is False
    assert subject._control_path(plan, "result-valid").exists()


def _write_r195_a1_spent_claim(plan, projection):
    a1_plan = dataclasses.replace(plan, attempt=1)
    identity = subject.preview(a1_plan, projection)
    claim = {
        **identity,
        "owner_launch_authority_mode": "exact_exploratory_signature_waiver",
        "owner_launch_waiver_schema": "arv2-six-universe-r195-settlement-waiver-v1",
        "owner_launch_waiver_id": subject._CANDIDATES["R195"].waiver_id,
        "owner_waived_payload_sha256": hashlib.sha256(
            subject._waiver_payload(a1_plan, identity, None)
        ).hexdigest(),
        "r193_lineage_look_number": 5,
        "owner_explicit_additional_look": True,
        "matched_baseline_target_path_sha256": None,
    }
    subject._write(subject._control_path(a1_plan, "claim"), claim)
    return claim


def _fake_r195_a2_qc(monkeypatch, plan, projection, *, source_drift=False,
                     prior_backtest=False):
    files = {item.project_path: item.source_bytes.decode("ascii")
             for item in projection.source_files}
    calls = []
    state = {"launched": False, "statistics": None}

    def post(_api, endpoint, payload):
        calls.append(endpoint)
        if endpoint == "authenticate":
            return {"success": True}
        if endpoint == "projects/read":
            assert payload == {"projectId": subject._R195_A2_PROJECT_ID}
            return {"success": True, "projects": [{
                "projectId": subject._R195_A2_PROJECT_ID,
                "name": plan.project_name,
                "organizationId": plan.organization_id,
                "language": "Py", "owner": True, "codeRunning": False,
                "collaborators": [{"owner": True}],
            }]}
        if endpoint == "files/read":
            observed = dict(files)
            if source_drift:
                observed["main.py"] += "# drift"
            return {"success": True, "files": [{
                "projectId": subject._R195_A2_PROJECT_ID,
                "name": name, "content": content,
            } for name, content in observed.items()]}
        if endpoint == "backtests/list":
            assert payload == {
                "projectId": subject._R195_A2_PROJECT_ID,
                "includeStatistics": False,
            }
            rows = ([{"projectId": subject._R195_A2_PROJECT_ID,
                      "backtestId": "prior", "name": "prior",
                      "status": "Completed."}] if prior_backtest else
                    [{"projectId": subject._R195_A2_PROJECT_ID,
                      "backtestId": "r195-a2", "name": plan.backtest_name,
                      "status": "Completed."}] if state["launched"] else [])
            return {"success": True, "count": len(rows), "backtests": rows}
        if endpoint == "compile/create":
            assert subject._control_path(plan, "claim").exists()
            return {"success": True, "compileId": "r195-a2-compile"}
        if endpoint == "compile/read":
            return {"success": True, "compileId": "r195-a2-compile",
                    "state": "BuildSuccess"}
        if endpoint == "backtests/create":
            assert subject._control_path(plan, "claim").exists()
            state["launched"] = True
            return {"success": True, "backtest": {
                "projectId": subject._R195_A2_PROJECT_ID,
                "backtestId": "r195-a2", "name": plan.backtest_name,
                "status": "In Queue...",
            }}
        if endpoint == "backtests/read":
            assert state["statistics"] is not None
            return {"success": True, "backtest": {
                "projectId": subject._R195_A2_PROJECT_ID,
                "backtestId": "r195-a2", "name": plan.backtest_name,
                "status": "Completed.", "statistics": state["statistics"],
            }}
        raise AssertionError(endpoint)

    monkeypatch.setattr(subject, "_client", lambda _api: None)
    monkeypatch.setattr(subject, "_post", post)
    return calls, state


def test_r195_a2_exact_recovery_launch_and_result(
    projections, tmp_path, monkeypatch,
):
    projection = projections["R195"]
    plan = dataclasses.replace(_plan(tmp_path, projection, "R195"), attempt=2)
    _predecessors(monkeypatch, plan)
    _write_r195_a1_spent_claim(plan, projection)
    waiver = json.loads(subject.render_owner_waiver_payload(plan, projection))
    assert waiver["attempt"] == 2
    assert waiver["project_id"] == subject._R195_A2_PROJECT_ID
    assert waiver["r193_lineage_look_number"] == 6
    assert waiver["r193_prior_looks_spent"] == 5
    assert waiver["r195_prior_attempts_spent"] == 1
    assert waiver["mutating_endpoint_budget"] == {
        "compile/create": 1, "backtests/create": 1,
    }
    assert waiver["source_upload_authorized"] is False
    calls, qc = _fake_r195_a2_qc(monkeypatch, plan, projection)
    launch = subject.launch_r195_a2(
        plan, projection, object(),
        owner_waiver_id=subject._R195_A2_WAIVER_ID,
    )
    assert launch["attempt"] == 2
    assert launch["r193_lineage_look_number"] == 6
    assert launch["r193_prior_looks_spent"] == 5
    assert launch["r195_prior_attempts_spent"] == 1
    assert calls == [
        "authenticate", "projects/read", "files/read", "backtests/list",
        "compile/create", "compile/read", "backtests/create",
    ]
    assert subject.poll_status(plan, launch, object()) == "Completed."
    qc["statistics"] = _statistics(plan, launch, target_path="d" * 64)
    result = subject.read_aggregates_once(plan, launch, object())
    assert result["run_valid"] is True
    receipt = subject._read(subject._control_path(plan, "result-valid"))
    assert receipt["attempt"] == 2
    assert receipt["r193_lineage_look_number"] == 6
    assert receipt["r193_prior_looks_spent"] == 5
    assert receipt["r195_prior_attempts_spent"] == 1
    assert receipt["matched_baseline_target_path_sha256"] == "d" * 64
    with pytest.raises(subject.SixUniverseSettlementSubmissionError,
                       match="already claimed"):
        subject.launch_r195_a2(
            plan, projection, object(),
            owner_waiver_id=subject._R195_A2_WAIVER_ID,
        )
    with pytest.raises(subject.SixUniverseSettlementSubmissionError,
                       match="already claimed"):
        subject.read_aggregates_once(plan, launch, object())


@pytest.mark.parametrize("defect", (
    "source_drift", "prior_backtest", "a1_claim_tamper", "wrong_waiver",
))
def test_r195_a2_refuses_before_any_mutation(
    projections, tmp_path, monkeypatch, defect,
):
    projection = projections["R195"]
    plan = dataclasses.replace(_plan(tmp_path, projection, "R195"), attempt=2)
    _predecessors(monkeypatch, plan)
    _write_r195_a1_spent_claim(plan, projection)
    calls, _ = _fake_r195_a2_qc(
        monkeypatch, plan, projection,
        source_drift=defect == "source_drift",
        prior_backtest=defect == "prior_backtest",
    )
    if defect == "a1_claim_tamper":
        real_read = subject._read
        a1_path = subject._control_path(dataclasses.replace(plan, attempt=1), "claim")
        monkeypatch.setattr(subject, "_read", lambda path: (
            dict(real_read(path), r193_lineage_look_number=1)
            if path == a1_path else real_read(path)
        ))
    with pytest.raises(subject.SixUniverseSettlementSubmissionError):
        subject.launch_r195_a2(
            plan, projection, object(),
            owner_waiver_id=("wrong" if defect == "wrong_waiver"
                             else subject._R195_A2_WAIVER_ID),
        )
    assert not any(name in calls for name in (
        "projects/create", "files/delete", "files/create", "files/update",
        "compile/create", "backtests/create",
    ))
    assert not subject._control_path(plan, "claim").exists()


@pytest.mark.parametrize("candidate_id", (
    "R196", "R197", "R198", "R199", "R200",
    "R201", "R202",
))
@pytest.mark.parametrize("same_path", (True, False))
def test_r195_a2_posthoc_receipt_comparison_keeps_read_time_flag(
    projections, tmp_path, monkeypatch, candidate_id, same_path,
):
    projection = projections[candidate_id]
    plan = _plan(tmp_path, projection, candidate_id)
    _predecessors(monkeypatch, plan)
    _, qc = _fake_qc(monkeypatch, plan, projection)
    launch = subject.launch_a1(
        plan, projection, object(),
        owner_waiver_id=subject._CANDIDATES[candidate_id].waiver_id,
    )
    assert subject.poll_status(plan, launch, object()) == "Completed."
    qc["statistics"] = _statistics(plan, launch, target_path="d" * 64)
    result = subject.read_aggregates_once(plan, launch, object())
    assert result["run_valid"] is True
    assert result["comparison_valid"] is False

    anchor_projection = projections["R195"]
    anchor_plan = dataclasses.replace(
        _plan(tmp_path, anchor_projection, "R195"), attempt=2,
    )
    _write_r195_a1_spent_claim(anchor_plan, anchor_projection)
    _, anchor_qc = _fake_r195_a2_qc(
        monkeypatch, anchor_plan, anchor_projection,
    )
    anchor_launch = subject.launch_r195_a2(
        anchor_plan, anchor_projection, object(),
        owner_waiver_id=subject._R195_A2_WAIVER_ID,
    )
    assert subject.poll_status(anchor_plan, anchor_launch, object()) == "Completed."
    anchor_qc["statistics"] = _statistics(
        anchor_plan, anchor_launch,
        target_path="d" * 64 if same_path else "e" * 64,
    )
    assert subject.read_aggregates_once(
        anchor_plan, anchor_launch, object(),
    )["run_valid"] is True
    comparison = subject.compare_valid_receipts(plan)
    assert comparison["comparison_valid"] is same_path
    assert comparison["r195_anchor_attempt"] == 2
    assert comparison["matched_baseline_target_path_sha256"] == "d" * 64
    assert comparison["r195_matched_baseline_target_path_sha256"] == (
        "d" * 64 if same_path else "e" * 64
    )
    # The later candidate's one-use receipt remains a historical read-time fact.
    assert subject._read(subject._control_path(plan, "result-valid"))[
        "comparison_valid"
    ] is False
