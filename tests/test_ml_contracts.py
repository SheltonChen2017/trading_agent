"""Tests for ml/contracts.py -- strategy doc section 5.5's ML-1 test list:
manifest round trip; rejection of missing required fields; rejection of
unknown schema versions; rejection of NaN/infinity; unavailable output when
features are missing; deterministic IDs/hashes for identical canonical
inputs; different hash for any behavior-relevant change.
"""
from __future__ import annotations

import math

import pytest

from assistant.schemas import EvidenceStatus
from ml.contracts import (
    ContractError,
    DatasetManifest,
    ModelManifest,
    PredictionRecord,
    require_matching_feature_order,
)
from ml.hashing import hash_payload


def _dataset_manifest_kwargs(**overrides):
    kwargs = dict(
        dataset_id="ds-1",
        created_at="2026-07-31T00:00:00+00:00",
        task="volatility_forecast",
        feature_set_version="fs-1",
        label_version="lv-1",
        source_descriptions=("yfinance daily bars",),
        point_in_time_data=False,
        requested_start_date="2020-01-01",
        requested_end_date="2026-07-31",
        actual_start_date="2020-01-02",
        actual_end_date="2026-07-30",
        row_count=100,
        distinct_session_count=100,
        ticker_count=1,
        universe_definition="fixed:v1",
        entry_timing="next_open",
        target_horizon_sessions=20,
        embargo_sessions=20,
        transaction_cost_bps=5.0,
        tax_assumptions="none",
        input_hashes={"prices": "abc123"},
        dataset_hash="def456",
        git_commit="0123456789abcdef",
    )
    kwargs.update(overrides)
    return kwargs


def _model_manifest_kwargs(**overrides):
    kwargs = dict(
        model_id="model-1",
        model_version="0.1.0",
        task="volatility_forecast",
        created_at="2026-07-31T00:00:00+00:00",
        dataset_id="ds-1",
        dataset_hash="def456",
        feature_set_version="fs-1",
        ordered_feature_names=("realized_vol_20d", "realized_vol_60d"),
        label_version="lv-1",
        algorithm="ewma_baseline",
        hyperparameters={"halflife": 20},
        random_seed=42,
        training_window={"start": "2020-01-01", "end": "2025-01-01"},
        validation_windows=({"start": "2025-01-01", "end": "2025-06-01"},),
        dependency_versions={"scikit-learn": "1.9.0"},
        artifact_hash="artifacthash",
        evaluation_report_hash="reporthash",
        evidence_status=EvidenceStatus.EXPLORATORY,
    )
    kwargs.update(overrides)
    return kwargs


def _prediction_kwargs(**overrides):
    kwargs = dict(
        prediction_id="pred-1",
        model_id="model-1",
        model_version="0.1.0",
        artifact_hash="artifacthash",
        dataset_or_feature_snapshot_hash="snaphash",
        task="volatility_forecast",
        subject_key="NVDA",
        as_of_session="2026-07-30",
        generated_at="2026-07-31T00:00:00+00:00",
        horizon_sessions=20,
        values={"annualized_volatility_pct": 24.3},
        uncertainty={"prediction_interval_pct": [18.1, 33.7]},
        data_available_at="2026-07-30T20:00:00+00:00",
        feature_freshness={"realized_vol_20d": "2026-07-30"},
        available=True,
        refusal_reasons=(),
        evidence_status=EvidenceStatus.EXPLORATORY,
    )
    kwargs.update(overrides)
    return kwargs


# --- DatasetManifest ---------------------------------------------------


def test_dataset_manifest_round_trips_through_to_dict_and_from_dict():
    manifest = DatasetManifest(**_dataset_manifest_kwargs())
    restored = DatasetManifest.from_dict(manifest.to_dict())
    assert restored == manifest


def test_dataset_manifest_rejects_unknown_schema_version():
    with pytest.raises(ContractError, match="unknown schema_version"):
        DatasetManifest(**_dataset_manifest_kwargs(schema_version="99.0"))


def test_dataset_manifest_rejects_missing_required_field():
    kwargs = _dataset_manifest_kwargs()
    del kwargs["dataset_id"]
    with pytest.raises(ContractError):
        DatasetManifest.from_dict(kwargs)


def test_dataset_manifest_rejects_non_finite_transaction_cost():
    with pytest.raises(ContractError, match="not finite"):
        DatasetManifest(**_dataset_manifest_kwargs(transaction_cost_bps=math.nan))


def test_dataset_manifest_rejects_non_finite_nested_input_hash_value_is_a_noop_for_strings():
    # input_hashes values are strings (hex digests), not numeric -- confirm
    # the finite-check walks the structure without misfiring on strings.
    manifest = DatasetManifest(**_dataset_manifest_kwargs(input_hashes={"prices": "abc"}))
    assert manifest.input_hashes == {"prices": "abc"}


def test_dataset_manifest_deterministic_hash_for_identical_canonical_input():
    a = DatasetManifest(**_dataset_manifest_kwargs())
    b = DatasetManifest(**_dataset_manifest_kwargs())
    assert hash_payload(a.to_dict()) == hash_payload(b.to_dict())


def test_dataset_manifest_hash_changes_for_behavior_relevant_change():
    a = DatasetManifest(**_dataset_manifest_kwargs())
    b = DatasetManifest(**_dataset_manifest_kwargs(target_horizon_sessions=60))
    assert hash_payload(a.to_dict()) != hash_payload(b.to_dict())


# --- ModelManifest -------------------------------------------------------


def test_model_manifest_round_trips_through_to_dict_and_from_dict():
    manifest = ModelManifest(**_model_manifest_kwargs())
    restored = ModelManifest.from_dict(manifest.to_dict())
    assert restored == manifest


def test_model_manifest_production_authoritative_is_always_false():
    manifest = ModelManifest(**_model_manifest_kwargs())
    assert manifest.production_authoritative is False
    assert manifest.to_dict()["production_authoritative"] is False
    # No constructor parameter exists for it at all.
    import inspect

    assert "production_authoritative" not in inspect.signature(ModelManifest).parameters


def test_model_manifest_rejects_duplicate_feature_names():
    with pytest.raises(ContractError, match="duplicates"):
        ModelManifest(
            **_model_manifest_kwargs(ordered_feature_names=("a", "a"))
        )


def test_model_manifest_rejects_empty_feature_names():
    with pytest.raises(ContractError, match="not be empty"):
        ModelManifest(**_model_manifest_kwargs(ordered_feature_names=()))


def test_model_manifest_rejects_non_evidence_status_enum():
    with pytest.raises(ContractError, match="EvidenceStatus"):
        ModelManifest(**_model_manifest_kwargs(evidence_status="exploratory"))


def test_model_manifest_rejects_non_finite_hyperparameter():
    with pytest.raises(ContractError, match="not finite"):
        ModelManifest(**_model_manifest_kwargs(hyperparameters={"lr": math.inf}))


def test_model_manifest_hash_changes_for_behavior_relevant_change():
    a = ModelManifest(**_model_manifest_kwargs())
    b = ModelManifest(**_model_manifest_kwargs(random_seed=43))
    assert hash_payload(a.to_dict()) != hash_payload(b.to_dict())


# --- PredictionRecord ------------------------------------------------------


def test_prediction_record_round_trips_through_to_dict_and_from_dict():
    record = PredictionRecord(**_prediction_kwargs())
    restored = PredictionRecord.from_dict(record.to_dict())
    assert restored == record


def test_prediction_record_production_authoritative_is_always_false():
    record = PredictionRecord(**_prediction_kwargs())
    assert record.production_authoritative is False
    assert record.to_dict()["production_authoritative"] is False
    import inspect

    assert "production_authoritative" not in inspect.signature(PredictionRecord).parameters


def test_prediction_record_unavailable_requires_a_refusal_reason():
    with pytest.raises(ContractError, match="refusal reason"):
        PredictionRecord(
            **_prediction_kwargs(available=False, values={}, uncertainty={}, refusal_reasons=())
        )


def test_prediction_record_unavailable_with_reason_is_accepted_with_empty_values():
    record = PredictionRecord(
        **_prediction_kwargs(
            available=False,
            values={},
            uncertainty={},
            refusal_reasons=("stale_features",),
        )
    )
    assert record.available is False
    assert record.refusal_reasons == ("stale_features",)


def test_prediction_record_available_cannot_carry_refusal_reasons():
    with pytest.raises(ContractError, match="must not carry refusal_reasons"):
        PredictionRecord(**_prediction_kwargs(available=True, refusal_reasons=("x",)))


def test_prediction_record_available_requires_non_empty_values():
    with pytest.raises(ContractError, match="must carry values"):
        PredictionRecord(**_prediction_kwargs(available=True, values={}))


def test_prediction_record_rejects_non_finite_value():
    with pytest.raises(ContractError, match="not finite"):
        PredictionRecord(
            **_prediction_kwargs(values={"annualized_volatility_pct": math.nan})
        )


def test_prediction_record_rejects_non_positive_horizon():
    with pytest.raises(ContractError, match="positive integer"):
        PredictionRecord(**_prediction_kwargs(horizon_sessions=0))


# --- require_matching_feature_order --------------------------------------


def test_require_matching_feature_order_accepts_exact_match():
    manifest = ModelManifest(**_model_manifest_kwargs())
    require_matching_feature_order(manifest, ["realized_vol_20d", "realized_vol_60d"])


def test_require_matching_feature_order_rejects_reordering():
    manifest = ModelManifest(**_model_manifest_kwargs())
    with pytest.raises(ContractError, match="feature order mismatch"):
        require_matching_feature_order(manifest, ["realized_vol_60d", "realized_vol_20d"])


def test_require_matching_feature_order_rejects_missing_feature():
    manifest = ModelManifest(**_model_manifest_kwargs())
    with pytest.raises(ContractError, match="feature order mismatch"):
        require_matching_feature_order(manifest, ["realized_vol_20d"])
