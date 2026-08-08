"""ML-LR-7 monitoring and promotion-dossier acceptance tests."""
from __future__ import annotations

import ast
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from ml.monitoring_reports import (
    MonitoringReportError,
    ShadowMonitoringGate,
    build_epoch_monitoring_report,
)
from ml.hashing import hash_payload
from ml.promotion import (
    PromotionDossier,
    PromotionDossierError,
    build_promotion_dossier,
    evidence_snapshot,
)


EPOCH = "epoch-a"


def _gate(**overrides):
    values = {
        "minimum_unique_dates": 3,
        "rolling_window_unique_dates": 2,
        "minimum_slice_unique_dates": 1,
        "minimum_regime_count": 2,
        "minimum_prediction_coverage": 1.0,
        "maximum_refusal_fraction": 0.1,
        "target_interval_coverage": 0.9,
        "interval_coverage_tolerance": 0.2,
        "mandate_ceiling_daily_pct": 2.0,
        "maximum_brier": 0.25,
        "maximum_feature_psi": 0.25,
        "maximum_output_mean_shift_fraction": 0.20,
        "minimum_model_better_date_fraction": 0.50,
        "sample_size_justification": (
            "Three fixture dates exercise frequency and overlap; production must "
            "replace this with an effect-size and power-derived year-plus gate."
        ),
    }
    values.update(overrides)
    return ShadowMonitoringGate(**values)


def _prediction(session: str, ticker: str, *, epoch: str = EPOCH, ewma=True):
    as_of = date.fromisoformat(session)
    target = as_of + timedelta(days=30)
    values = {
        "daily_volatility_pct": 1.0,
        "trailing_baseline_daily_pct": 1.2,
    }
    if ewma:
        values["ewma_baseline_daily_pct"] = 1.1
    return {
        "prediction_id": f"{session}-{ticker}",
        "model_key": "model:version",
        "task": "volatility_forecast",
        "subject_key": ticker,
        "as_of_session": session,
        "generated_at": f"{session}T21:00:00+00:00",
        "horizon_sessions": 20,
        "target_available_at": f"{target.isoformat()}T21:00:00+00:00",
        "feature_snapshot_hash": "a" * 64,
        "available": True,
        "refusal_reasons": [],
        "evidence_epoch": epoch,
        "prediction": {
            "values": values,
            "uncertainty": {
                "prediction_interval_daily_pct": [0.5, 1.8],
            },
            "feature_freshness": {
                "missing_count": 0,
                "stale_count": 0,
                "maximum_age_sessions": 0,
            },
            "monitoring_features": {"realized_vol_20d_pct": 1.0},
            "monitoring_context": {"event_category": "ordinary_session"},
        },
    }


def _run(session: str, *, status="completed"):
    return {
        "run_id": f"run-{session}",
        "scheduled_for": f"{session}T20:00:00+00:00",
        "status": status,
        "evidence_epoch": EPOCH,
    }


def _outcome(prediction, actual=1.05):
    return {
        "prediction_id": prediction["prediction_id"],
        "outcome": {"realized_daily_volatility_pct": actual},
    }


def _reference():
    return {
        "realized_vol_20d_pct": {
            "independent_date_count": 10,
            "bin_edges": [0.8, 1.0, 1.2],
            "bin_counts": [2, 3, 3, 2],
            "minimum": 0.5,
            "maximum": 1.5,
            "mean": 1.0,
            "standard_deviation": 0.2,
        }
    }


def _report(*, omit_ewma=False, alerts=()):
    sessions = ("2026-01-05", "2026-01-06", "2026-01-07")
    predictions = [
        _prediction(session, ticker, ewma=not (omit_ewma and session == sessions[0] and ticker == "B"))
        for session in sessions
        for ticker in ("A", "B")
    ]
    return build_epoch_monitoring_report(
        evidence_epoch=EPOCH,
        lineage_hash="b" * 64,
        predictions=predictions,
        outcomes=[_outcome(row) for row in predictions],
        runs=[_run(session) for session in sessions],
        operational_alerts=alerts,
        expected_subjects=("A", "B"),
        feature_reference=_reference(),
        gate=_gate(),
        as_of="2026-03-01T00:00:00+00:00",
    )


def test_overlapping_ticker_rows_count_as_three_dates_not_six():
    report = _report()
    assert report["coverage"]["recorded_subject_attempt_count"] == 6
    assert report["coverage"]["unique_scheduled_date_count"] == 3
    assert report["realized_error"]["independent_unique_date_count"] == 3
    assert report["frozen_baseline_performance"]["comparisons"]["ewma"][
        "independent_unique_date_count"
    ] == 3
    assert report["independent_observation_unit"] == "unique_as_of_session"


def test_duplicate_predictions_cannot_inflate_coverage_and_are_blocking():
    sessions = ("2026-01-05", "2026-01-06", "2026-01-07")
    predictions = [_prediction(session, "A") for session in sessions]
    predictions.extend([dict(predictions[0]), dict(predictions[0])])
    report = build_epoch_monitoring_report(
        evidence_epoch=EPOCH,
        lineage_hash="b" * 64,
        predictions=predictions,
        outcomes=[_outcome(row) for row in predictions[:3]],
        runs=[_run(session) for session in sessions],
        operational_alerts=[],
        expected_subjects=("A",),
        feature_reference=_reference(),
        gate=_gate(),
        as_of="2026-03-01T00:00:00+00:00",
    )

    assert report["coverage"]["prediction_coverage"] == 1.0
    assert report["coverage"]["recorded_subject_attempt_count"] == 3
    assert report["lineage_consistency"]["duplicate_generation_count"] == 1
    assert "shadow_lineage_inconsistent" in report["promotion_blockers"]


def test_duplicate_outcomes_are_excluded_and_block_monitoring():
    sessions = ("2026-01-05", "2026-01-06", "2026-01-07")
    predictions = [_prediction(session, "A") for session in sessions]
    outcomes = [_outcome(row) for row in predictions]
    outcomes.append(_outcome(predictions[0], actual=9.0))
    report = build_epoch_monitoring_report(
        evidence_epoch=EPOCH,
        lineage_hash="b" * 64,
        predictions=predictions,
        outcomes=outcomes,
        runs=[_run(session) for session in sessions],
        operational_alerts=[],
        expected_subjects=("A",),
        feature_reference=_reference(),
        gate=_gate(),
        as_of="2026-03-01T00:00:00+00:00",
    )

    assert report["duplicate_outcome_count"] == 1
    assert "shadow_duplicate_outcomes" in report["promotion_blockers"]
    assert report["realized_error"]["independent_unique_date_count"] == 2


def test_two_epochs_cannot_be_pooled_into_one_monitoring_report():
    first = _prediction("2026-01-05", "A")
    second = _prediction("2026-01-06", "A", epoch="epoch-b")
    with pytest.raises(MonitoringReportError, match="different evidence epochs"):
        build_epoch_monitoring_report(
            evidence_epoch=EPOCH,
            lineage_hash="b" * 64,
            predictions=[first, second],
            outcomes=[],
            runs=[_run("2026-01-05")],
            operational_alerts=[],
            expected_subjects=("A",),
            feature_reference=_reference(),
            gate=_gate(),
        )


def test_missing_baseline_rows_are_visible_and_block_the_comparison():
    report = _report(omit_ewma=True)
    comparison = report["frozen_baseline_performance"]["comparisons"]["ewma"]
    assert comparison["missing_baseline_row_count"] == 1
    assert not comparison["sample_sufficiency"]["sufficient"]
    assert "ewma_baseline_comparison_insufficient" in report["promotion_blockers"]


def test_complete_baseline_sample_cannot_hide_model_underperformance():
    sessions = ("2026-01-05", "2026-01-06", "2026-01-07")
    predictions = [
        _prediction(session, ticker)
        for session in sessions
        for ticker in ("A", "B")
    ]
    report = build_epoch_monitoring_report(
        evidence_epoch=EPOCH,
        lineage_hash="b" * 64,
        predictions=predictions,
        outcomes=[_outcome(row, actual=1.2) for row in predictions],
        runs=[_run(session) for session in sessions],
        operational_alerts=[],
        expected_subjects=("A", "B"),
        feature_reference=_reference(),
        gate=_gate(),
        as_of="2026-03-01T00:00:00+00:00",
    )
    comparison = report["frozen_baseline_performance"]["comparisons"]["ewma"]
    assert comparison["missing_baseline_row_count"] == 0
    assert comparison["sample_sufficiency"]["sufficient"]
    assert not comparison["performance_gate_passed"]
    assert "model_underperforms_ewma_in_shadow" in report["promotion_blockers"]


def test_feature_drift_counts_out_of_training_range_observations():
    sessions = ("2026-01-05", "2026-01-06", "2026-01-07")
    predictions = [_prediction(session, "A") for session in sessions]
    for prediction in predictions:
        prediction["prediction"]["monitoring_features"]["realized_vol_20d_pct"] = 10.0
    report = build_epoch_monitoring_report(
        evidence_epoch=EPOCH,
        lineage_hash="b" * 64,
        predictions=predictions,
        outcomes=[_outcome(row) for row in predictions],
        runs=[_run(session) for session in sessions],
        operational_alerts=[],
        expected_subjects=("A",),
        feature_reference=_reference(),
        gate=_gate(),
        as_of="2026-03-01T00:00:00+00:00",
    )
    drift = report["feature_distribution_drift"]["features"]["realized_vol_20d_pct"]
    assert drift["out_of_training_range_count"] == 3
    assert not drift["drift_acceptable"]
    assert "feature_distribution_drift_unacceptable" in report["promotion_blockers"]


def test_calibration_averages_row_brier_within_date_before_counting_dates():
    sessions = ("2026-01-05", "2026-01-06", "2026-01-07")
    predictions = [
        _prediction(session, ticker)
        for session in sessions
        for ticker in ("A", "B")
    ]
    for prediction in predictions:
        prediction["prediction"]["uncertainty"][
            "calibrated_probability_above_mandate_ceiling"
        ] = 0.9 if prediction["subject_key"] == "A" else 0.1
    outcomes = [
        _outcome(row, actual=2.5 if row["subject_key"] == "A" else 1.5)
        for row in predictions
    ]
    report = build_epoch_monitoring_report(
        evidence_epoch=EPOCH,
        lineage_hash="b" * 64,
        predictions=predictions,
        outcomes=outcomes,
        runs=[_run(session) for session in sessions],
        operational_alerts=[],
        expected_subjects=("A", "B"),
        feature_reference=_reference(),
        gate=_gate(),
        as_of="2026-03-01T00:00:00+00:00",
    )
    calibration = report["calibration_and_interval_coverage"][
        "ceiling_probability"
    ]
    assert calibration["independent_unique_date_count"] == 3
    assert calibration["brier_score"] == pytest.approx(0.01)


def test_historical_incident_remains_visible_after_later_successful_runs():
    alert = {
        "alert_id": 1,
        "status": "acknowledged",
        "category": "ml_shadow",
        "message": "provider failed once",
    }
    report = _report(alerts=(alert,))
    operations = report["operational_failures"]
    assert operations["historical_incident_count"] == 1
    assert operations["unresolved_incident_count"] == 0
    assert operations["clean"]


def test_unrelated_alert_does_not_cover_a_failed_shadow_run():
    sessions = ("2026-01-05", "2026-01-06", "2026-01-07")
    predictions = [_prediction(session, "A") for session in sessions]
    unrelated = {
        "status": "acknowledged",
        "category": "ml_shadow",
        "details": {"run_id": "some-other-run"},
    }
    report = build_epoch_monitoring_report(
        evidence_epoch=EPOCH,
        lineage_hash="b" * 64,
        predictions=predictions,
        outcomes=[_outcome(row) for row in predictions],
        runs=[_run(sessions[0], status="failed"), *[_run(s) for s in sessions[1:]]],
        operational_alerts=[unrelated],
        expected_subjects=("A",),
        feature_reference=_reference(),
        gate=_gate(),
        as_of="2026-03-01T00:00:00+00:00",
    )

    assert report["operational_failures"]["untracked_failed_run_count"] == 1
    assert "shadow_operational_incidents_present" in report["promotion_blockers"]


def test_missing_confirmation_economics_calibration_and_lineage_are_blockers():
    dossier = build_promotion_dossier(
        generated_at="2026-08-01T12:00:00+00:00",
        task="volatility_forecast",
        model_key="model:version",
        evidence_epoch=EPOCH,
        evidence={
            "shadow_monitoring_report": evidence_snapshot(
                sha256="1" * 64,
                result={
                    "evidence_epoch": EPOCH,
                    "production_authoritative": False,
                    "promotion_blockers": ["calibration_insufficient_or_unacceptable"],
                },
            )
        },
        known_limitations=("fixture only",),
        unresolved_incidents=(),
        proposed_adapter_scope={},
    )
    blockers = set(dossier.promotion_blockers)
    assert "missing_confirmation_specification" in blockers
    assert "missing_economic_simulation" in blockers
    assert "calibration_insufficient_or_unacceptable" in blockers
    assert "artifact_hash_lineage_unverified" in blockers
    assert "separate_owner_promotion_review_required" in blockers


def test_caller_mutation_cannot_change_a_hashed_dossier():
    evidence = {
        "shadow_monitoring_report": evidence_snapshot(
            sha256="1" * 64,
            result={
                "evidence_epoch": EPOCH,
                "production_authoritative": False,
                "promotion_blockers": [],
                "nested": {"value": 1},
            },
        )
    }
    limitations = ["first"]
    dossier = build_promotion_dossier(
        generated_at="2026-08-01T12:00:00+00:00",
        task="volatility_forecast",
        model_key="model:version",
        evidence_epoch=EPOCH,
        evidence=evidence,
        known_limitations=limitations,
        unresolved_incidents=(),
        proposed_adapter_scope={"consumer": "read_only_status"},
    )
    before = dossier.to_dict()
    evidence["shadow_monitoring_report"]["result"]["nested"]["value"] = 999
    limitations.append("mutated")
    assert dossier.to_dict() == before
    restored = PromotionDossier.from_dict(before)
    assert restored.to_dict() == before

    forged = dict(before)
    forged["eligible_for_separate_owner_review"] = not before[
        "eligible_for_separate_owner_review"
    ]
    forged_without_hash = {
        key: value for key, value in forged.items() if key != "dossier_hash"
    }
    forged["dossier_hash"] = hash_payload(forged_without_hash)
    with pytest.raises(PromotionDossierError, match="inconsistent with blockers"):
        PromotionDossier.from_dict(forged)


def test_dossier_rejects_monitoring_from_another_epoch():
    with pytest.raises(PromotionDossierError, match="different evidence epoch"):
        build_promotion_dossier(
            generated_at="2026-08-01T12:00:00+00:00",
            task="volatility_forecast",
            model_key="model:version",
            evidence_epoch=EPOCH,
            evidence={
                "shadow_monitoring_report": evidence_snapshot(
                    sha256="1" * 64,
                    result={
                        "evidence_epoch": "epoch-b",
                        "production_authoritative": False,
                        "promotion_blockers": [],
                    },
                )
            },
            known_limitations=(),
            unresolved_incidents=(),
            proposed_adapter_scope={},
        )


def test_promotion_module_has_no_registry_or_execution_imports():
    path = Path(__file__).resolve().parent.parent / "ml" / "promotion.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    forbidden = (
        "assistant.storage",
        "assistant.execution_service",
        "assistant.research_registry",
        "execution",
        "risk.execution_gate",
    )
    assert not [name for name in imports if name.startswith(forbidden)]
