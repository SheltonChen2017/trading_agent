"""Doc 15.3's required integration test, end to end:

  build a small immutable dataset from fixture data; train and evaluate a
  baseline model; save, hash, reload, and score it; persist a shadow
  prediction idempotently; attach an outcome only after maturity; generate
  a monitoring report; and PROVE that no proposal, authorization, broker
  call, or execution state is created anywhere in that flow.

Plus doc 15.2's pure-noise check at the whole-pipeline level.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from assistant.schemas import EvidenceStatus
from assistant.storage import AssistantStore
from ml.artifacts import load_model_artifact, save_model_artifact, save_model_manifest
from ml.contracts import ModelManifest, require_matching_feature_order
from ml.datasets import (
    assemble_dataset_frames,
    build_dataset_manifest,
    join_for_evaluation,
    load_dataset,
    save_dataset,
)
from ml.evaluation import beats_baseline_in_multiple_folds, date_level_spearman_ic, summarize_information_coefficient
from ml.features import compute_point_in_time_features
from ml.labels import compute_forward_excess_return_labels
from ml.monitoring import build_monitoring_report
from ml.splits import purged_grouped_walk_forward_splits
from ml.volatility import (
    build_volatility_training_matrix,
    evaluate_volatility_models,
    fit_log_volatility_regression,
    predict_volatility,
)


def _synthetic_ohlcv(n: int, seed: int, *, drift: float = 0.0003) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2024-01-01", periods=n)
    returns = rng.normal(drift, 0.015, n)
    close = 100.0 * np.cumprod(1 + returns)
    open_ = close * (1 + rng.normal(0, 0.002, n))
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) * 1.005,
            "low": np.minimum(open_, close) * 0.995,
            "close": close,
            "volume": rng.integers(1_000_000, 3_000_000, n).astype(float),
        },
        index=index,
    )


def _fixture_universe(n: int = 420):
    tickers = ["AAA", "BBB", "CCC"]
    prices = {t: _synthetic_ohlcv(n, seed=i) for i, t in enumerate(tickers)}
    benchmarks = {
        name: _synthetic_ohlcv(n, seed=100 + i)
        for i, name in enumerate(("QQQ", "SOXX", "SPY"))
    }
    return tickers, prices, benchmarks


def test_end_to_end_dataset_model_shadow_and_monitoring_creates_no_execution_state(tmp_path):
    tickers, prices, benchmark_frames = _fixture_universe()
    benchmarks = {name: frame["close"] for name, frame in benchmark_frames.items()}

    # --- 1. build a small immutable dataset from fixture data --------------
    features, labels, dropped_total = {}, {}, 0
    for ticker in tickers:
        features[ticker] = compute_point_in_time_features(
            ticker, prices[ticker], benchmarks=benchmarks
        )
        rows, dropped = compute_forward_excess_return_labels(
            ticker,
            prices[ticker]["close"],
            prices[ticker]["open"],
            benchmark_frames["QQQ"]["close"],
            benchmark_open=benchmark_frames["QQQ"]["open"],
            horizon_sessions=20,
        )
        labels[ticker] = rows
        dropped_total += dropped

    features_df, labels_df = assemble_dataset_frames(features, labels)
    label_version = labels_df["label_version"].iloc[0]
    manifest = build_dataset_manifest(
        features_df=features_df,
        labels_df=labels_df,
        dataset_id="integration-ds-1",
        created_at="2026-07-31T00:00:00+00:00",
        task="excess_return_ranking",
        feature_set_version="fs-v1",
        label_version=label_version,
        source_descriptions=("synthetic fixture",),
        point_in_time_data=False,
        universe_definition="fixed:test",
        entry_timing="next_open",
        target_horizon_sessions=20,
        embargo_sessions=20,
        dropped_label_row_count=dropped_total,
        transaction_cost_bps=5.0,
        tax_assumptions="none",
        git_commit="0" * 40,
    )
    save_dataset(features_df, labels_df, manifest, directory=tmp_path)

    # --- 2. reload it, hash-verified --------------------------------------
    reloaded_features, reloaded_labels, reloaded_manifest = load_dataset(
        tmp_path, "integration-ds-1"
    )
    assert reloaded_manifest == manifest
    assert reloaded_manifest.dropped_label_row_count == dropped_total

    joined = join_for_evaluation(
        reloaded_features, reloaded_labels, label_version=label_version
    )
    assert len(joined) > 0

    # --- 3. purged walk-forward folds -------------------------------------
    folds = purged_grouped_walk_forward_splits(
        list(joined["as_of_session"]),
        list(joined["label_exit_session"]),
        n_splits=3,
        embargo_sessions=20,
    )
    assert len(folds) == 3
    for fold in folds:
        # No training row's label may reach into its validation window.
        for row_index in fold.train_row_indices:
            assert joined["label_exit_session"].iloc[row_index] < fold.validation_start

    # --- 4. train and evaluate a baseline model ---------------------------
    frame = joined.copy()
    frame["target_vol"] = frame["realized_vol_20d_pct"].abs() + 1.0
    feature_columns = ["realized_vol_10d_pct", "realized_vol_60d_pct"]
    frame = frame.dropna(subset=feature_columns + ["target_vol"]).reset_index(drop=True)

    folds_for_model = purged_grouped_walk_forward_splits(
        list(frame["as_of_session"]),
        list(frame["label_exit_session"]),
        n_splits=2,
        embargo_sessions=20,
    )
    fold_metrics = evaluate_volatility_models(
        frame,
        folds_for_model,
        feature_columns=feature_columns,
        target_column="target_vol",
        trailing_baseline_column="realized_vol_10d_pct",
        ewma_baseline_column="realized_vol_60d_pct",
    )
    assert len(fold_metrics) == 2

    comparison = beats_baseline_in_multiple_folds(
        fold_metrics, candidate_key="gbm_qlike", baseline_key="ewma_qlike"
    )
    assert "passes" in comparison  # reported, never auto-acted upon

    # --- 5. save, hash, reload, and score the model artifact --------------
    train_frame = frame.iloc[list(folds_for_model[0].train_row_indices)]
    x_train, y_train, ordered = build_volatility_training_matrix(
        train_frame, feature_columns=feature_columns, target_column="target_vol"
    )
    model = fit_log_volatility_regression(x_train, y_train)
    artifact_hash = save_model_artifact(model, directory=tmp_path, filename="m.joblib")
    model_manifest = ModelManifest(
        model_id="integration-vol",
        model_version="0.1.0",
        task="volatility_forecast",
        created_at="2026-07-31T00:00:00+00:00",
        dataset_id=manifest.dataset_id,
        dataset_hash=manifest.dataset_hash,
        feature_set_version="fs-v1",
        ordered_feature_names=ordered,
        label_version=label_version,
        algorithm="ridge_on_log_volatility",
        hyperparameters={"alpha": 1.0},
        random_seed=0,
        training_window={"start": "2024-01-01", "end": "2025-01-01"},
        validation_windows=({"start": "2025-01-02", "end": "2025-06-01"},),
        dependency_versions={"scikit-learn": "1.9.0"},
        artifact_hash=artifact_hash,
        evaluation_report_hash="b" * 64,
        evidence_status=EvidenceStatus.EXPLORATORY,
    )
    save_model_manifest(model_manifest, directory=tmp_path, filename="m.manifest.json")
    reloaded_model = load_model_artifact(
        model_manifest, directory=tmp_path, filename="m.joblib"
    )
    require_matching_feature_order(model_manifest, feature_columns)
    scored = predict_volatility(reloaded_model, x_train[:5])
    assert np.all(scored > 0)
    assert model_manifest.production_authoritative is False

    # --- 6. persist a shadow prediction, idempotently ---------------------
    store = AssistantStore(tmp_path / "assistant.db")
    store.register_ml_model("integration-vol:0.1.0", model_manifest.to_dict())
    prediction_payload = {
        "model_key": "integration-vol:0.1.0",
        "task": "volatility_forecast",
        "subject_key": "AAA",
        "as_of_session": "2026-07-31",
        "generated_at": "2026-07-31T21:00:00+00:00",
        "horizon_sessions": 20,
        "feature_snapshot_hash": manifest.dataset_hash,
        "available": True,
        "values": {"annualized_volatility_pct": float(scored[0])},
    }
    first = store.record_ml_prediction(prediction_payload)
    second = store.record_ml_prediction(prediction_payload)
    assert first["prediction_id"] == second["prediction_id"]
    assert len(store.list_ml_predictions()) == 1

    # A refusal is recorded too, not only successes.
    store.record_ml_prediction(
        {**prediction_payload, "subject_key": "BBB", "available": False,
         "refusal_reasons": ["stale_features"]}
    )

    # --- 7. attach an outcome only after maturity -------------------------
    with pytest.raises(ValueError, match="precedes"):
        store.record_ml_prediction_outcome(
            first["prediction_id"], {"realized": 1.0}, matured_at="2026-01-01"
        )
    store.record_ml_prediction_outcome(
        first["prediction_id"], {"realized_vol_pct": 22.0}, matured_at="2026-08-28"
    )
    assert len(store.list_ml_prediction_outcomes()) == 1

    # --- 8. generate a monitoring report ----------------------------------
    report = build_monitoring_report(store.list_ml_predictions())
    assert report["coverage"]["total_attempts"] == 2
    assert report["coverage"]["refused_count"] == 1
    assert "never retrains" in report["notes"]

    # --- 9. PROVE no execution state was created --------------------------
    assert store.list_proposals() == []
    assert store.list_ai_runs() == []
    with store._connect() as connection:
        for table in (
            "trade_proposals", "broker_orders", "broker_order_events",
            "execution_reservations", "allocation_batches",
        ):
            count = connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            assert count == 0, f"{table} must be empty after a pure-ML flow, got {count}"


def test_pure_noise_end_to_end_produces_no_false_claim_of_skill():
    """Doc 18 'Foundation complete': 'a pure-noise end-to-end test produces
    no false claim of skill.' Scores are independent of outcomes, so
    date-level IC must sit near zero and the sign must not be consistent."""
    rng = np.random.default_rng(1234)
    rows = []
    for date in pd.bdate_range("2026-01-01", periods=120):
        for i in range(12):
            rows.append(
                {
                    "as_of_session": str(date.date()),
                    "ticker": f"T{i}",
                    "score": float(rng.normal()),
                    "outcome": float(rng.normal()),
                }
            )
    panel = pd.DataFrame(rows)

    ic = date_level_spearman_ic(panel, score_column="score", outcome_column="outcome")
    summary = summarize_information_coefficient(ic)

    assert summary["date_count"] == 120
    assert abs(summary["mean_ic"]) < 0.06
    assert 0.35 < summary["positive_date_fraction"] < 0.65


def test_a_future_only_feature_is_powerful_but_the_real_builder_refuses_it():
    """Doc 15.2: 'a future-only feature must look powerful if leakage is
    allowed and be rejected by the real builder.'

    First half: prove the leak WOULD look like strong skill, so the test
    cannot pass vacuously. Second half: prove ml/features.py never produces
    such a column -- its point-in-time guarantee is what makes the leak
    unconstructible from real feature output.
    """
    rng = np.random.default_rng(7)
    rows = []
    for date in pd.bdate_range("2026-01-01", periods=60):
        for i in range(10):
            outcome = float(rng.normal())
            rows.append(
                {
                    "as_of_session": str(date.date()),
                    "ticker": f"T{i}",
                    "leaked_score": outcome,  # the future, used as a feature
                    "outcome": outcome,
                }
            )
    leaked = pd.DataFrame(rows)
    leaked_ic = summarize_information_coefficient(
        date_level_spearman_ic(
            leaked, score_column="leaked_score", outcome_column="outcome"
        )
    )
    assert leaked_ic["mean_ic"] > 0.99  # leakage looks like perfect skill

    # The real builder cannot produce that column: every feature it emits is
    # computed from windows ending at the row's own session.
    _, prices, benchmark_frames = _fixture_universe(300)
    features = compute_point_in_time_features(
        "AAA", prices["AAA"], benchmarks={k: v["close"] for k, v in benchmark_frames.items()}
    )
    assert "leaked_score" not in features.columns
    prefix = compute_point_in_time_features(
        "AAA",
        prices["AAA"].iloc[:200],
        benchmarks={k: v["close"].iloc[:200] for k, v in benchmark_frames.items()},
    )
    numeric = [c for c in prefix.columns if c not in ("ticker", "as_of_session", "market_trend")]
    np.testing.assert_allclose(
        prefix[numeric].to_numpy(dtype=float),
        features[numeric].iloc[:200].to_numpy(dtype=float),
        equal_nan=True,
    )
