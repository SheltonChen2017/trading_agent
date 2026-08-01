"""ML-LR-8: the read-only presentation surface.

The risk this milestone introduces is not a wrong number -- it is a
*correct* number that a reader takes for more than it is. So most of these
tests assert refusals: that an interval which was never recorded stays
unavailable, that a stale attempt is never dressed up as current, that
missing monitoring evidence reads as a blocker rather than a clean bill of
health, and that nothing the surface emits is shaped like an instruction.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ml.hashing import hash_payload
from ml.presentation import (
    EXPERIMENTAL_LABEL,
    PresentationError,
    assert_no_action_shaped_keys,
    build_observation,
    build_presentation,
    latest_attempt_by_subject,
    verify_monitoring_report,
)
from scripts import run_ml_shadow
from tests.test_ml_shadow_runtime import _registered_store

EPOCH = "volatility_forecast:demo:1.0.0:abcd"
OTHER_EPOCH = "volatility_forecast:demo:1.0.0:9999"


def _prediction(
    *,
    subject: str = "AAA",
    session: str = "2026-02-25",
    generated_at: str = "2026-02-25T21:05:00+00:00",
    epoch: str = EPOCH,
    available: bool = True,
    refusals: tuple[str, ...] = (),
    uncertainty: dict | None = None,
    values: dict | None = None,
) -> dict:
    return {
        "prediction_id": f"{subject}-{session}",
        "subject_key": subject,
        "as_of_session": session,
        "generated_at": generated_at,
        "horizon_sessions": 20,
        "evidence_epoch": epoch,
        "available": available,
        "refusal_reasons": list(refusals),
        "prediction": {
            "task": "volatility_forecast",
            "model_id": "demo",
            "model_version": "1.0.0",
            "evidence_status": "exploratory",
            "values": values
            if values is not None
            else {
                "daily_volatility_pct": 0.95,
                "annualized_volatility_pct": 15.0,
                "trailing_baseline_daily_pct": 0.046,
                "ewma_baseline_daily_pct": 0.137,
            },
            "uncertainty": uncertainty
            if uncertainty is not None
            else {
                "status": "refer_to_frozen_evaluation_report",
                "evaluation_report_hash": "40d2affc",
            },
            "feature_freshness": {
                "maximum_age_sessions": 0,
                "missing_count": 0,
                "stale_count": 0,
            },
        },
    }


def _report(*, epoch: str = EPOCH, blockers: list[str] | None = None) -> dict:
    payload = {
        "schema_version": "1.0",
        "evidence_epoch": epoch,
        "promotion_blockers": blockers
        if blockers is not None
        else ["coverage_evidence_insufficient", "interval_coverage_insufficient"],
        "conclusions_supported": False,
        "production_authoritative": False,
    }
    payload["report_hash"] = hash_payload(payload)
    return payload


# --- The label and the non-authority claim -------------------------------


def test_required_label_is_reproduced_exactly():
    assert EXPERIMENTAL_LABEL == (
        "Experimental model observation — not a recommendation and not used "
        "by the execution gate."
    )


def test_every_serialized_result_carries_the_label_and_is_non_authoritative():
    result = build_presentation(
        task="volatility_forecast",
        model_key="demo:1.0.0",
        evidence_epoch=EPOCH,
        epoch_status="active",
        predictions=[_prediction()],
        monitoring_report=_report(),
    )
    assert result["production_authoritative"] is False
    assert result["label"] == EXPERIMENTAL_LABEL
    for observation in result["observations"]:
        assert observation["production_authoritative"] is False
        assert observation["label"] == EXPERIMENTAL_LABEL


def test_no_serialized_field_is_shaped_like_a_trade_instruction():
    result = build_presentation(
        task="volatility_forecast",
        model_key="demo:1.0.0",
        evidence_epoch=EPOCH,
        epoch_status="active",
        predictions=[_prediction()],
        monitoring_report=_report(),
    )
    assert_no_action_shaped_keys(result)
    with pytest.raises(PresentationError):
        assert_no_action_shaped_keys({"observations": [{"side": "sell"}]})


# --- Nothing is reconstructed --------------------------------------------


def test_absent_prediction_interval_is_reported_unavailable_not_derived():
    observation = build_observation(_prediction(), evidence_epoch=EPOCH).to_dict()
    assert observation["prediction_interval"] == "unavailable"
    assert "not reconstructed" in observation["prediction_interval_reason"]


def test_frozen_evaluation_report_reference_is_not_treated_as_an_interval():
    # The stored `uncertainty` points at a retrospective report. Reading a
    # coverage number out of it and displaying it beside a prospective
    # estimate would be the single easiest way to mislead here.
    observation = build_observation(
        _prediction(
            uncertainty={
                "status": "refer_to_frozen_evaluation_report",
                "evaluation_report_hash": "deadbeef",
                "interval_coverage_pct": 91.4,
            }
        ),
        evidence_epoch=EPOCH,
    ).to_dict()
    assert observation["prediction_interval"] == "unavailable"
    assert "91.4" not in json.dumps(observation)


def test_uncalibrated_probability_is_never_presented_as_confidence():
    observation = build_observation(_prediction(), evidence_epoch=EPOCH).to_dict()
    assert observation["threshold_probability"] == "unavailable"
    assert observation["calibration_status"] == "not_measured"
    assert "confidence" not in json.dumps(observation).lower()


def test_prospectively_recorded_interval_is_displayed_when_it_exists():
    observation = build_observation(
        _prediction(
            uncertainty={
                "prediction_interval_daily_pct": [0.5, 1.4],
                "probability_above_ceiling": 0.23,
                "calibration_status": "calibrated_prospectively",
            }
        ),
        evidence_epoch=EPOCH,
    ).to_dict()
    assert observation["prediction_interval"] == "[0.500000, 1.400000]"
    assert observation["threshold_probability"] == "0.230000"
    assert observation["calibration_status"] == "calibrated_prospectively"


def test_both_frozen_baselines_are_displayed():
    observation = build_observation(_prediction(), evidence_epoch=EPOCH).to_dict()
    assert observation["trailing_baseline_daily_pct"] == 0.046
    assert observation["ewma_baseline_daily_pct"] == 0.137


# --- The latest attempt is the answer ------------------------------------


def test_unavailable_latest_attempt_never_falls_back_to_an_older_success():
    predictions = [
        _prediction(session="2026-02-24", generated_at="2026-02-24T21:05:00+00:00"),
        _prediction(
            session="2026-02-25",
            generated_at="2026-02-25T21:05:00+00:00",
            available=False,
            refusals=("price_data_stale",),
            values={},
        ),
    ]
    result = build_presentation(
        task="volatility_forecast",
        model_key="demo:1.0.0",
        evidence_epoch=EPOCH,
        epoch_status="active",
        predictions=predictions,
        monitoring_report=_report(),
    )
    observation = result["observations"][0]
    assert observation["available"] is False
    assert observation["refusal_reasons"] == ["price_data_stale"]
    assert observation["estimate_daily_volatility_pct"] is None
    assert (
        "latest_attempt_unavailable_for_at_least_one_subject"
        in result["promotion_blockers"]
    )


def test_refusal_reasons_and_feature_freshness_are_surfaced():
    observation = build_observation(
        _prediction(available=False, refusals=("missing_benchmark",)),
        evidence_epoch=EPOCH,
    ).to_dict()
    assert observation["refusal_reasons"] == ["missing_benchmark"]
    assert observation["feature_freshness"]["stale_count"] == 0


# --- Epochs are never pooled ---------------------------------------------


def test_predictions_from_another_evidence_epoch_are_excluded():
    predictions = [
        _prediction(session="2026-02-26", epoch=OTHER_EPOCH),
        _prediction(session="2026-02-25", epoch=EPOCH),
    ]
    latest = latest_attempt_by_subject(predictions, evidence_epoch=EPOCH)
    assert latest["AAA"]["as_of_session"] == "2026-02-25"


def test_building_an_observation_from_a_foreign_epoch_is_refused():
    with pytest.raises(PresentationError):
        build_observation(_prediction(epoch=OTHER_EPOCH), evidence_epoch=EPOCH)


def test_no_active_epoch_is_a_blocker_not_an_empty_display():
    result = build_presentation(
        task="volatility_forecast",
        model_key="demo:1.0.0",
        evidence_epoch=None,
        epoch_status=None,
        predictions=[_prediction()],
        monitoring_report=None,
    )
    assert result["presentation_available"] is False
    assert result["promotion_blockers"] == ["no_active_evidence_epoch"]
    assert result["production_authoritative"] is False


# --- Monitoring evidence is verified, and absence is not a pass ----------


def test_monitoring_report_hash_is_verified():
    verified = verify_monitoring_report(_report(), expected_epoch=EPOCH)
    assert verified["status"] == "verified"


def test_tampered_monitoring_report_is_visibly_rejected():
    report = _report()
    report["promotion_blockers"] = []  # the tamper a reader would most want
    rejected = verify_monitoring_report(report, expected_epoch=EPOCH)
    assert rejected["status"] == "rejected"
    assert "hash mismatch" in rejected["reason"]
    assert rejected["promotion_blockers"] == []


def test_monitoring_report_from_a_different_epoch_is_rejected():
    rejected = verify_monitoring_report(_report(epoch=OTHER_EPOCH), expected_epoch=EPOCH)
    assert rejected["status"] == "rejected"
    assert "evidence epoch" in rejected["reason"]


def test_unhashable_monitoring_report_is_rejected_rather_than_raising():
    report = {"evidence_epoch": EPOCH, "value": float("nan"), "report_hash": "x" * 64}
    rejected = verify_monitoring_report(report, expected_epoch=EPOCH)
    assert rejected["status"] == "rejected"


def test_missing_monitoring_report_adds_an_explicit_blocker():
    result = build_presentation(
        task="volatility_forecast",
        model_key="demo:1.0.0",
        evidence_epoch=EPOCH,
        epoch_status="active",
        predictions=[_prediction()],
        monitoring_report=None,
    )
    assert result["monitoring"]["status"] == "unavailable"
    assert "monitoring_evidence_unavailable" in result["promotion_blockers"]
    # Absence must never read as a clean result.
    assert result["promotion_blockers"] != []


def test_promotion_blockers_are_surfaced_verbatim_without_weakening():
    blockers = ["shadow_regime_span_insufficient", "matured_outcome_underfill"]
    result = build_presentation(
        task="volatility_forecast",
        model_key="demo:1.0.0",
        evidence_epoch=EPOCH,
        epoch_status="active",
        predictions=[_prediction()],
        monitoring_report=_report(blockers=blockers),
    )
    for blocker in blockers:
        assert blocker in result["promotion_blockers"]


# --- Multiple subjects ---------------------------------------------------


def test_every_configured_subject_is_displayed_including_ones_with_no_attempt():
    result = build_presentation(
        task="volatility_forecast",
        model_key="demo:1.0.0",
        evidence_epoch=EPOCH,
        epoch_status="active",
        predictions=[_prediction(subject="AAA")],
        monitoring_report=_report(),
        subjects=["AAA", "BBB"],
    )
    shown = {item["subject_key"]: item for item in result["observations"]}
    assert set(shown) == {"AAA", "BBB"}
    assert shown["BBB"]["available"] is False
    assert "no attempt recorded" in shown["BBB"]["refusal_reasons"][0]


# --- CLI integration: read-only, and additive to the existing status -----


def test_status_command_is_read_only_and_extends_the_existing_summary(tmp_path):
    store, config, _config_path, _artifact_dir, _provider, _manifest = _registered_store(
        tmp_path
    )
    database = tmp_path / "assistant.db"
    before = database.read_bytes()

    summary = run_ml_shadow.command_status(store, config)

    # Every pre-existing operational key survives.
    for key in (
        "registration_status",
        "active_evidence_epoch",
        "evidence_epoch_count",
        "run_status_counts",
        "prediction_count",
        "outcome_count",
        "open_ml_alert_count",
    ):
        assert key in summary
    assert summary["production_authoritative"] is False
    assert summary["presentation"]["production_authoritative"] is False
    assert database.read_bytes() == before, "status must not write to the database"


def test_status_task_flag_is_an_assertion_not_a_selector(tmp_path):
    store, config, *_rest = _registered_store(tmp_path)
    summary = run_ml_shadow.command_status(store, config, task="volatility_forecast")
    assert summary["ok"] is True
    with pytest.raises(run_ml_shadow.ShadowCommandError):
        run_ml_shadow.command_status(store, config, task="direction_ranker")


def test_status_rejects_an_unconfigured_subject(tmp_path):
    store, config, *_rest = _registered_store(tmp_path)
    with pytest.raises(run_ml_shadow.ShadowCommandError):
        run_ml_shadow.command_status(store, config, subject="NOT_A_SUBJECT")


def test_status_marks_an_unreadable_monitoring_report_as_rejected(tmp_path):
    store, config, *_rest = _registered_store(tmp_path)
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    summary = run_ml_shadow.command_status(store, config, monitoring_report=broken)
    assert summary["ok"] is True  # presentation failure never fails the command
    assert summary["presentation"]["monitoring"]["status"] == "rejected"
    assert "monitoring_report_rejected" in summary["presentation"]["promotion_blockers"]


def test_status_accepts_the_envelope_written_by_monitor_output(tmp_path):
    # `monitor --output` writes a CLI envelope, not a bare report. If the
    # surface could not read its own tool's file, the verified path would be
    # unreachable in practice.
    envelope = {"command": "monitor", "monitoring": _report()}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    loaded, error = run_ml_shadow._load_monitoring_report(path)
    assert error is None
    assert loaded["report_hash"] == _report()["report_hash"]


def test_status_rejects_an_evidence_epoch_belonging_to_another_model(tmp_path):
    store, config, *_rest = _registered_store(tmp_path)
    summary = run_ml_shadow.command_status(store, config, evidence_epoch="not-an-epoch")
    assert summary["ok"] is True
    presentation = summary["presentation"]
    assert presentation["presentation_available"] is False
    assert "requested_evidence_epoch_not_found" in presentation["promotion_blockers"]


def test_presentation_module_imports_no_storage_or_broker():
    source = Path(__file__).resolve().parent.parent / "ml" / "presentation.py"
    text = source.read_text(encoding="utf-8")
    for forbidden in ("assistant.storage", "assistant.broker", "alpaca", "execution"):
        assert f"import {forbidden}" not in text
