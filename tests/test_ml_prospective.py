from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ml.prospective import (
    DAILY_VOLATILITY_UNIT,
    ProspectiveContractError,
    ProspectiveInferenceContract,
    build_volatility_prospective_profile,
    derive_volatility_uncertainty,
)


def _profile():
    return build_volatility_prospective_profile(
        (
            {
                "actual": [1.0] * 30,
                "predicted": [0.8] * 15 + [1.2] * 15,
            },
        ),
        ceiling_calibration={
            "ceiling_pct": 1.1,
            "calibration_status": "experimental",
            "brier_score": 0.2,
            "event_count": 30,
        },
    )


def _lineage():
    return {
        "model_key": "model:1",
        "provider_id": "fixture:v1",
        "dataset_id": "dataset-v1",
        "dataset_hash": "a" * 64,
        "artifact_hash": "b" * 64,
        "evaluation_report_hash": "c" * 64,
        "feature_set_version": "fs-v1",
        "label_version": "label-v1",
        "configuration_hash": "d" * 64,
        "evidence_epoch": "epoch-v1",
        "shadow_run_id": "run-v1",
        "feature_snapshot_hash": "e" * 64,
        "schedule_version": "daily-v1",
    }


def test_oof_profile_drives_interval_and_experimental_probability():
    profile = _profile()
    derived = derive_volatility_uncertainty(1.0, profile)
    lower, upper = derived["prediction_interval_daily_pct"]
    assert lower <= 1.0 <= upper
    assert 0 <= derived["threshold_probability"] <= 1
    assert derived["probability_label"] == "experimental_probability"
    assert derived["profile_hash"]


def test_no_preregistered_ceiling_cannot_be_reconstructed_later():
    profile = build_volatility_prospective_profile(
        ({"actual": [1.0] * 30, "predicted": [1.0] * 30},),
        ceiling_calibration={"calibration_status": "not_measured"},
    )
    assert profile["threshold"]["status"] == "unavailable"
    with pytest.raises(ProspectiveContractError, match="threshold probability"):
        derive_volatility_uncertainty(1.0, profile)


def test_available_contract_requires_complete_non_authoritative_evidence():
    derived = derive_volatility_uncertainty(1.0, _profile())
    contract = ProspectiveInferenceContract(
        prediction_id="mlpred-1",
        task="volatility_forecast",
        subject_key="AAA",
        as_of_session="2026-02-25",
        generated_at="2026-02-25T21:05:00+00:00",
        horizon_sessions=20,
        target_available_at="2026-03-25T20:00:00+00:00",
        point_estimate={"value": 1.0, "unit": DAILY_VOLATILITY_UNIT},
        prediction_interval={
            "lower": derived["prediction_interval_daily_pct"][0],
            "upper": derived["prediction_interval_daily_pct"][1],
        },
        threshold_probability={
            "value": derived["threshold_probability"],
            "label": derived["probability_label"],
        },
        calibration={"status": "experimental"},
        frozen_baselines={"trailing_daily_pct": 1.1, "ewma_daily_pct": 1.2},
        feature_observations=({
            "name": "realized_vol_20d_pct",
            "value": 1.0,
            "available_at": "2026-02-25T21:00:00+00:00",
            "age_sessions": 0,
            "missing": False,
        },),
        reference_distribution={"status": "available", "identity_hash": "f" * 64},
        regime_category="at_or_below_training_mean",
        event_category="ordinary_session",
        lineage=_lineage(),
        available=True,
    )
    assert contract.to_dict()["production_authoritative"] is False


def test_action_shaped_feature_is_refused():
    derived = derive_volatility_uncertainty(1.0, _profile())
    with pytest.raises(ProspectiveContractError, match="action-shaped"):
        ProspectiveInferenceContract(
            prediction_id="mlpred-1",
            task="volatility_forecast",
            subject_key="AAA",
            as_of_session="2026-02-25",
            generated_at="2026-02-25T21:05:00+00:00",
            horizon_sessions=20,
            target_available_at="2026-03-25T20:00:00+00:00",
            point_estimate={"value": 1.0, "unit": DAILY_VOLATILITY_UNIT},
            prediction_interval={
                "lower": derived["prediction_interval_daily_pct"][0],
                "upper": derived["prediction_interval_daily_pct"][1],
            },
            threshold_probability={"value": 0.5, "label": "experimental_probability"},
            calibration={"status": "experimental"},
            frozen_baselines={"trailing_daily_pct": 1.1, "ewma_daily_pct": 1.2},
            feature_observations=({
                "name": "shares", "value": 10.0,
                "available_at": "2026-02-25T21:00:00+00:00",
                "age_sessions": 0, "missing": False,
            },),
            reference_distribution={"status": "available", "identity_hash": "f" * 64},
            regime_category="normal",
            event_category="ordinary_session",
            lineage=_lineage(),
            available=True,
        )


def test_prospective_module_has_no_execution_imports():
    tree = ast.parse(Path("ml/prospective.py").read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(name.startswith(("execution", "assistant")) for name in imported)
