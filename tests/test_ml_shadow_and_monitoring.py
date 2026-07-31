"""Tests for ML-6: the shadow-prediction storage tables plus
ml/monitoring.py. Doc 10 requires idempotent prediction insertion, outcomes
only after maturity, refusals logged alongside successes, and monitoring
that cannot retrain or promote anything."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from assistant.storage import AssistantStore
from ml.monitoring import (
    MonitoringError,
    build_monitoring_report,
    coverage_report,
    distribution_drift,
    feature_health_report,
    lineage_consistency,
    realized_error_by_window,
)


def _prediction(**overrides):
    payload = {
        "model_key": "vol:0.1.0",
        "task": "volatility_forecast",
        "subject_key": "NVDA",
        "as_of_session": "2026-07-31",
        "generated_at": "2026-07-31T21:00:00+00:00",
        "horizon_sessions": 20,
        "target_available_at": "2026-08-28T20:00:00+00:00",
        "data_available_at": "2026-07-31T20:00:00+00:00",
        "feature_freshness": {
            "maximum_age_sessions": 0, "missing_count": 0, "stale_count": 0,
        },
        "feature_snapshot_hash": "a" * 64,
        "evidence_status": "exploratory",
        "production_authoritative": False,
        "available": True,
        "values": {"annualized_volatility_pct": 30.0},
    }
    payload.update(overrides)
    return payload


# --- storage: position snapshots (doc 8.1) ---------------------------------


def test_position_snapshots_round_trip_with_exact_decimal_text(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    store.append_portfolio_position_snapshots(
        [
            {
                "account_key": "paper", "session_date": "2026-07-31",
                "captured_at": "2026-07-31T20:00:00+00:00", "ticker": "NVDA",
                "shares": "10.5", "market_value": "2100.25", "price": "200.0238",
                "source": "alpaca",
            }
        ]
    )
    rows = store.list_portfolio_position_snapshots("paper")
    assert len(rows) == 1
    # Exact decimal text, not a float that would corrupt a reconstructed weight.
    assert rows[0]["market_value"] == "2100.25"
    assert rows[0]["price"] == "200.0238"


def test_position_snapshots_deduplicate_identical_captures(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    snapshot = {
        "account_key": "paper", "session_date": "2026-07-31",
        "captured_at": "2026-07-31T20:00:00+00:00", "ticker": "NVDA",
        "shares": "10", "market_value": "2000", "price": "200", "source": "alpaca",
    }
    store.append_portfolio_position_snapshots([snapshot])
    store.append_portfolio_position_snapshots([snapshot])
    assert len(store.list_portfolio_position_snapshots("paper")) == 1


def test_position_snapshots_filter_by_session(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    for date in ("2026-07-30", "2026-07-31"):
        store.append_portfolio_position_snapshots(
            [{
                "account_key": "paper", "session_date": date,
                "captured_at": f"{date}T20:00:00+00:00", "ticker": "NVDA",
                "shares": "10", "market_value": "2000", "price": "200", "source": "alpaca",
            }]
        )
    assert len(store.list_portfolio_position_snapshots("paper")) == 2
    assert len(
        store.list_portfolio_position_snapshots("paper", session_date="2026-07-31")
    ) == 1


def test_position_snapshot_conflict_is_rejected_not_silently_hidden(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    snapshot = {
        "account_key": "paper", "session_date": "2026-07-31",
        "captured_at": "2026-07-31T20:00:00+00:00", "ticker": "NVDA",
        "shares": "10", "market_value": "2000", "price": "200",
        "source": "alpaca",
    }
    store.append_portfolio_position_snapshots([snapshot])
    with pytest.raises(ValueError, match="different immutable position snapshot"):
        store.append_portfolio_position_snapshots(
            [{**snapshot, "shares": "11", "market_value": "2200"}]
        )


def test_position_snapshot_requires_market_date_and_finite_economics(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    base = {
        "account_key": "paper", "session_date": "2026-07-31",
        "captured_at": "2026-07-31T20:00:00+00:00", "ticker": "NVDA",
        "shares": "10", "market_value": "2000", "price": "200",
    }
    with pytest.raises(ValueError, match="session_date"):
        store.append_portfolio_position_snapshots(
            [{**base, "captured_at": "2026-08-01T20:00:00+00:00"}]
        )
    with pytest.raises(ValueError, match="finite decimal"):
        store.append_portfolio_position_snapshots([{**base, "price": "NaN"}])


# --- storage: model registration (doc 10.1) --------------------------------


def test_model_registration_defaults_to_shadow_status(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    registration = store.register_ml_model("vol:0.1.0", {"model_id": "vol"})
    assert registration["status"] == "shadow"
    assert len(registration["manifest_hash"]) == 64


def test_model_registration_refuses_a_production_status(tmp_path):
    """Doc 3.1: 'no model status automatically becomes production authority.'"""
    store = AssistantStore(tmp_path / "a.db")
    with pytest.raises(ValueError, match="separate, explicit promotion"):
        store.register_ml_model("vol:0.1.0", {}, status="production")


def test_model_registration_is_idempotent(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    first = store.register_ml_model("vol:0.1.0", {"model_id": "vol"})
    second = store.register_ml_model("vol:0.1.0", {"model_id": "vol"})
    assert second == first


def test_model_registration_rejects_conflicting_manifest(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    store.register_ml_model("vol:0.1.0", {"model_id": "vol"})
    with pytest.raises(ValueError, match="new versioned model_key"):
        store.register_ml_model("vol:0.1.0", {"model_id": "DIFFERENT"})


# --- storage: predictions (doc 10.2) ---------------------------------------


def test_prediction_insertion_is_idempotent_and_never_rewrites(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    store.register_ml_model("vol:0.1.0", {"model_id": "vol"})
    first = store.record_ml_prediction(_prediction())
    second = store.record_ml_prediction(_prediction())
    assert second["prediction_id"] == first["prediction_id"]
    assert len(store.list_ml_predictions()) == 1


def test_prediction_conflict_is_rejected_instead_of_hidden(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    store.register_ml_model("vol:0.1.0", {"model_id": "vol"})
    store.record_ml_prediction(_prediction())
    with pytest.raises(ValueError, match="different prediction already exists"):
        store.record_ml_prediction(
        _prediction(values={"annualized_volatility_pct": 99.9},
                    generated_at="2026-07-31T23:00:00+00:00")
        )
    assert len(store.list_ml_predictions()) == 1


def test_a_different_session_is_a_different_prediction(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    store.register_ml_model("vol:0.1.0", {"model_id": "vol"})
    store.record_ml_prediction(
        _prediction(
            as_of_session="2026-07-30",
            generated_at="2026-07-30T21:00:00+00:00",
            data_available_at="2026-07-30T20:00:00+00:00",
        )
    )
    store.record_ml_prediction(_prediction(as_of_session="2026-07-31"))
    assert len(store.list_ml_predictions()) == 2


def test_unavailable_predictions_are_recorded_with_reasons(tmp_path):
    """Doc 10.2: 'Record unavailable predictions and their reasons; do not
    log only successes.'"""
    store = AssistantStore(tmp_path / "a.db")
    store.register_ml_model("vol:0.1.0", {"model_id": "vol"})
    stored = store.record_ml_prediction(
        _prediction(
            available=False, values={}, evidence_status="unavailable",
            refusal_reasons=["stale_features"],
        )
    )
    assert stored["available"] is False
    assert stored["refusal_reasons"] == ["stale_features"]


def test_unavailable_prediction_without_a_reason_is_refused(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    store.register_ml_model("vol:0.1.0", {"model_id": "vol"})
    with pytest.raises(ValueError, match="refusal reason"):
        store.record_ml_prediction(
            _prediction(available=False, values={}, evidence_status="unavailable")
        )


# --- storage: outcomes (doc 10.1) ------------------------------------------


def test_outcome_cannot_exist_before_its_prediction(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    with pytest.raises(ValueError, match="cannot"):
        store.record_ml_prediction_outcome("ghost", {"x": 1}, matured_at="2026-08-28")


def test_outcome_cannot_predate_the_prediction_session(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    store.register_ml_model("vol:0.1.0", {"model_id": "vol"})
    stored = store.record_ml_prediction(_prediction())
    with pytest.raises(ValueError, match="precedes"):
        store.record_ml_prediction_outcome(
            stored["prediction_id"], {"realized": 1.0},
            matured_at="2026-08-27T20:00:00+00:00",
        )


def test_matured_outcome_attaches_and_lists(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    store.register_ml_model("vol:0.1.0", {"model_id": "vol"})
    stored = store.record_ml_prediction(_prediction())
    store.record_ml_prediction_outcome(
        stored["prediction_id"], {"realized_vol_pct": 28.4},
        matured_at="2026-08-28T20:00:00+00:00",
    )
    outcomes = store.list_ml_prediction_outcomes()
    assert len(outcomes) == 1
    assert outcomes[0]["outcome"]["realized_vol_pct"] == 28.4


def test_outcome_is_immutable_and_unavailable_attempts_never_mature(tmp_path):
    store = AssistantStore(tmp_path / "a.db")
    store.register_ml_model("vol:0.1.0", {"model_id": "vol"})
    available = store.record_ml_prediction(_prediction())
    store.record_ml_prediction_outcome(
        available["prediction_id"], {"realized_vol_pct": 28.4},
        matured_at="2026-08-28T20:00:00+00:00",
    )
    with pytest.raises(ValueError, match="different immutable outcome"):
        store.record_ml_prediction_outcome(
            available["prediction_id"], {"realized_vol_pct": 99.0},
            matured_at="2026-08-28T20:00:00+00:00",
        )

    unavailable = store.record_ml_prediction(
        _prediction(
            subject_key="MSFT", available=False, values={},
            evidence_status="unavailable", refusal_reasons=["stale_features"],
        )
    )
    with pytest.raises(ValueError, match="unavailable prediction"):
        store.record_ml_prediction_outcome(
            unavailable["prediction_id"], {"realized_vol_pct": 20.0},
            matured_at="2026-08-28T20:00:00+00:00",
        )


# --- monitoring (doc 10.3) -------------------------------------------------


def test_coverage_report_counts_refusals_and_their_reasons():
    predictions = (
        [{"available": True, "refusal_reasons": []}] * 3
        + [{"available": False, "refusal_reasons": ["stale_features"]}] * 2
    )
    report = coverage_report(predictions)
    assert report["total_attempts"] == 5
    assert report["refused_count"] == 2
    assert report["refusal_rate"] == pytest.approx(0.4)
    assert report["refusal_reason_counts"] == {"stale_features": 2}
    assert not report["sufficient_sample"]  # only 5 observations


def test_coverage_report_handles_no_predictions():
    report = coverage_report([])
    assert report["total_attempts"] == 0
    assert report["refusal_rate"] is None
    assert not report["sufficient_sample"]


def test_feature_health_reads_persisted_prediction_payloads():
    predictions = [
        {
            "prediction": {
                "feature_freshness": {
                    "missing_count": 1,
                    "stale_count": 2,
                    "maximum_age_sessions": 3,
                }
            }
        }
    ]
    report = feature_health_report(predictions)
    assert report["missing_feature_count"] == 1
    assert report["stale_feature_count"] == 2
    assert report["maximum_age_sessions"] == 3


def test_distribution_drift_flags_a_real_shift_and_not_a_stable_one():
    rng = np.random.default_rng(0)
    reference = rng.normal(0, 1, 500)
    same = rng.normal(0, 1, 500)
    shifted = rng.normal(4, 1, 500)

    assert distribution_drift(reference, same)["interpretation"] == "stable"
    assert distribution_drift(reference, shifted)["interpretation"] == "significant_shift"


def test_distribution_drift_reports_its_interpretation_bands():
    rng = np.random.default_rng(0)
    drift = distribution_drift(rng.normal(size=200), rng.normal(size=200))
    assert "0.10" in drift["interpretation_bands"]


def test_distribution_drift_is_unavailable_for_empty_or_constant_input():
    assert distribution_drift([], [1.0])["psi"] is None
    constant = distribution_drift([5.0] * 100, [5.0] * 100)
    assert constant["psi"] is None
    assert constant["interpretation"] == "unavailable"


def test_realized_error_reports_bias_and_rolling_mae():
    sessions = [stamp.date().isoformat() for stamp in pd.bdate_range(
        "2026-01-01", periods=40
    )]
    matured = [
        {"as_of_session": session, "predicted": 10.0, "actual": 12.0}
        for session in sessions
    ]
    report = realized_error_by_window(matured, predicted_key="predicted", actual_key="actual")
    assert report["observation_count"] == 40
    assert report["overall_mae"] == pytest.approx(2.0)
    assert report["overall_bias"] == pytest.approx(2.0)  # systematically under-predicting
    assert report["sufficient_sample"]


def test_realized_error_rejects_a_tiny_window():
    with pytest.raises(MonitoringError, match="window"):
        realized_error_by_window([], predicted_key="p", actual_key="a", window=1)


def test_lineage_detects_a_model_change_and_requires_a_new_epoch():
    predictions = [
        {"model_key": "vol:0.1.0", "task": "t", "subject_key": "A",
         "as_of_session": "2026-01-01", "horizon_sessions": 20},
        {"model_key": "vol:0.2.0", "task": "t", "subject_key": "A",
         "as_of_session": "2026-01-02", "horizon_sessions": 20},
    ]
    lineage = lineage_consistency(predictions)
    assert lineage["model_changed_mid_stream"]
    assert lineage["requires_new_evidence_epoch"]


def test_lineage_detects_duplicate_generation_and_clock_errors():
    identity = {"model_key": "m", "task": "t", "subject_key": "A",
                "as_of_session": "2026-01-05", "horizon_sessions": 20}
    predictions = [
        {**identity, "generated_at": "2026-01-05T21:00:00+00:00"},
        {**identity, "generated_at": "2026-01-05T22:00:00+00:00"},
        # generated BEFORE its own as_of_session -- a clock error
        {**identity, "subject_key": "B", "generated_at": "2026-01-01T00:00:00+00:00"},
    ]
    lineage = lineage_consistency(predictions)
    assert lineage["duplicate_generation_count"] == 1
    assert lineage["clock_error_count"] == 1


def test_monitoring_report_is_read_only_and_states_so():
    report = build_monitoring_report(
        [{"available": True, "model_key": "m", "task": "t", "subject_key": "A",
          "as_of_session": "2026-01-01", "horizon_sessions": 20,
          "generated_at": "2026-01-01T21:00:00+00:00",
          "feature_snapshot_hash": "a" * 64}]
    )
    assert "never retrains" in report["notes"]
    assert not report["conclusions_supported_by_sample_size"]  # 1 observation
    for key in ("coverage", "lineage", "realized_error", "output_drift"):
        assert key in report
    assert report["production_authoritative"] is False


def test_monitoring_report_is_json_serializable():
    import json

    json.dumps(build_monitoring_report([]))
