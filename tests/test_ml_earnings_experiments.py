"""ML-LR-4 event-model runner and point-in-time fixture integration."""
from __future__ import annotations

import json
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import pytest

from ml.artifacts import load_model_artifact, load_model_manifest
from ml.availability import (
    FeatureAvailabilityRecord,
    UniverseMembershipRecord,
    evaluate_point_in_time_coverage,
    hash_feature_value,
)
from ml.datasets import assemble_dataset_frames, build_dataset_manifest, save_dataset
from ml.earnings_experiments import (
    BASELINES,
    CANDIDATES,
    EarningsExperimentError,
    build_typed_forecast,
    validate_earnings_spec,
)
from ml.experiment_contracts import ExperimentSpec, ResearchGateSpec
from ml.experiments import run_experiment
from ml.hashing import hash_payload
from ml.labels import LabelRow

FEATURES = ("pre_event_volatility_pct", "pre_event_residual_momentum_pct")


def _spec(**overrides) -> ExperimentSpec:
    values = dict(
        experiment_id="earnings-discovery-v1",
        task="earnings_gap_forecast",
        mode="discovery",
        created_at="2026-07-31T00:00:00+00:00",
        primary_outcome="event-date out-of-fold Brier/MAE versus frozen baselines",
        candidate_models=CANDIDATES,
        frozen_baselines=BASELINES,
        feature_set_version="earnings-fs-v1",
        label_version="earnings-gap-v1",
        benchmark="QQQ",
        horizon_sessions=1,
        universe_definition="earnings-fixture-v1",
        research_look_dimensions={"models": list(CANDIDATES), "horizons": ["1"]},
        split_configuration={"n_splits": 2, "embargo_sessions": 1},
        cost_tax_liquidity_assumptions={"transaction_cost_bps": 0.0},
        research_gate=ResearchGateSpec(
            minimum_folds_won=2,
            minimum_coverage_fraction=0.9,
            maximum_alpha=0.05,
            block_lengths=(5,),
            required_calibration_bins=5,
            failure_slices=(
                "ticker", "industry", "year", "volatility_regime", "release_timing",
            ),
        ),
        random_seed=7,
        ordered_feature_names=FEATURES,
        target_column="label_value",
        baseline_columns={},
        task_parameters={
            "absolute_gap_threshold_pct": 5.0,
            "downside_gap_threshold_pct": -5.0,
            "classification_probability_threshold": 0.55,
            "quantiles": [0.1, 0.5, 0.9],
            "minimum_group_baseline_events": 3,
            "confirmation_minimum_distinct_events": 150,
            "confirmation_minimum_upside_tail_events": 30,
            "confirmation_minimum_downside_tail_events": 30,
            "confirmation_sample_justification": (
                "Power analysis must justify 150 untouched events and 30 per tail."
            ),
        },
    )
    values.update(overrides)
    return ExperimentSpec(**values)


def _fixture_frames(n_dates: int = 150):
    rng = np.random.default_rng(11)
    event_dates = pd.bdate_range("2024-01-03", periods=n_dates)
    tickers = ("AAA", "BBB")
    industries = {"AAA": "Semiconductors", "BBB": "Software"}
    pattern = np.asarray([-10.0, -8.0, -3.0, 2.0, 4.0, 7.0, 9.0, 11.0])
    features_by_ticker: dict[str, pd.DataFrame] = {}
    labels_by_ticker: dict[str, tuple[LabelRow, ...]] = {}
    for ticker_index, ticker in enumerate(tickers):
        records = []
        labels = []
        for index, event_date in enumerate(event_dates):
            session = str(event_date.date())
            exit_session = str(
                event_dates[min(index + 1, len(event_dates) - 1)].date()
            )
            gap = float(pattern[(index + ticker_index) % len(pattern)])
            announced_at = f"{session}T21:30:00+00:00"
            records.append(
                {
                    "ticker": ticker,
                    "as_of_session": session,
                    "event_id": hash_payload(
                        {
                            "ticker": ticker,
                            "announced_at_utc": announced_at,
                            "source_id": "point-in-time-fixture",
                            "source_event_id": f"{ticker}-{session}",
                        }
                    ),
                    "event_date": session,
                    "industry": industries[ticker],
                    "release_timing": "after_close",
                    "announced_at_utc": announced_at,
                    "pre_event_volatility_pct": round(
                        abs(gap) + rng.normal(0, 0.15), 6
                    ),
                    "pre_event_residual_momentum_pct": round(
                        gap + rng.normal(0, 0.15), 6
                    ),
                }
            )
            labels.append(
                LabelRow(
                    ticker=ticker,
                    as_of_session=session,
                    label_version="earnings-gap-v1",
                    entry_session=session,
                    entry_price=100.0,
                    exit_session=exit_session,
                    exit_price=100.0 + gap,
                    value=gap,
                    components={"signed_gap_pct": gap},
                )
            )
        features_by_ticker[ticker] = pd.DataFrame(records)
        labels_by_ticker[ticker] = tuple(labels)
    return assemble_dataset_frames(features_by_ticker, labels_by_ticker)


def _build_point_in_time_dataset(directory: Path):
    features, labels = _fixture_frames()
    feature_columns = [column for column in features if column not in {"ticker", "as_of_session"}]
    availability = []
    cutoffs: dict[str, str] = {}
    feature_values = {}
    for row in features.itertuples(index=False):
        cutoff = f"{row.as_of_session}T20:00:00+00:00"
        cutoffs[row.as_of_session] = cutoff
        for feature_name in feature_columns:
            value = getattr(row, feature_name)
            feature_values[(row.as_of_session, row.ticker, feature_name)] = value
            availability.append(
                FeatureAvailabilityRecord(
                    as_of_session=row.as_of_session,
                    ticker=row.ticker,
                    feature_name=feature_name,
                    event_at=f"{row.as_of_session}T19:00:00+00:00",
                    available_at=f"{row.as_of_session}T19:01:00+00:00",
                    observed_at=cutoff,
                    source_id="point-in-time-fixture",
                    source_version="1.0",
                    revision_id="r1",
                    raw_value_hash=hash_feature_value(value),
                )
            )
    universe = [
        UniverseMembershipRecord(
            universe_id="earnings-fixture-v1",
            ticker=ticker,
            effective_from="2020-01-01",
            effective_to=None,
            announced_at="2019-12-01T00:00:00+00:00",
            available_at="2019-12-01T00:00:00+00:00",
            source_id="point-in-time-fixture",
            source_version="1.0",
        )
        for ticker in ("AAA", "BBB")
    ]
    feature_keys = [
        (str(row.as_of_session), str(row.ticker))
        for row in features[["as_of_session", "ticker"]].itertuples(index=False)
    ]
    coverage = evaluate_point_in_time_coverage(
        feature_keys=feature_keys,
        feature_columns=feature_columns,
        availability=availability,
        universe=universe,
        universe_id="earnings-fixture-v1",
        decision_cutoffs=cutoffs,
        feature_values=feature_values,
    )
    availability_df = pd.DataFrame([record.to_dict() for record in availability])
    universe_df = pd.DataFrame([record.to_dict() for record in universe])
    manifest = build_dataset_manifest(
        features_df=features,
        labels_df=labels,
        dataset_id="earnings-fixture",
        created_at="2026-07-31T00:00:00+00:00",
        task="earnings_gap_forecast",
        feature_set_version="earnings-fs-v1",
        label_version="earnings-gap-v1",
        source_descriptions=("fixture with explicit pre-event availability",),
        point_in_time_data=False,
        universe_definition="earnings-fixture-v1",
        entry_timing="overnight_gap",
        target_horizon_sessions=1,
        embargo_sessions=1,
        dropped_label_row_count=0,
        transaction_cost_bps=0.0,
        tax_assumptions="not applicable to risk forecast",
        git_commit="0" * 40,
        benchmark="QQQ",
        availability_df=availability_df,
        universe_df=universe_df,
        coverage=coverage,
    )
    assert manifest.point_in_time_data is True
    save_dataset(
        features,
        labels,
        manifest,
        directory=directory,
        availability_df=availability_df,
        universe_df=universe_df,
    )
    return manifest


def test_earnings_spec_freezes_order_and_task_parameters():
    spec = _spec()
    assert spec.task_parameters["classification_probability_threshold"] == 0.55
    assert ExperimentSpec.from_dict(spec.to_dict()) == spec
    changed = dict(spec.task_parameters)
    changed["classification_probability_threshold"] = 0.60
    assert _spec(task_parameters=changed).spec_hash != spec.spec_hash
    with pytest.raises(TypeError):
        spec.task_parameters["classification_probability_threshold"] = 0.60
    with pytest.raises(EarningsExperimentError, match="complete frozen order"):
        # Contract construction is valid; the task owns the stricter order rule.
        validate_earnings_spec(
            _spec(candidate_models=tuple(reversed(CANDIDATES)))
        )


def test_point_in_time_fixture_runner_emits_complete_event_report(tmp_path):
    dataset_directory = tmp_path / "dataset"
    output_directory = tmp_path / "output"
    manifest = _build_point_in_time_dataset(dataset_directory)
    record = run_experiment(
        _spec(),
        dataset_directory,
        output_directory,
        "0" * 40,
        dataset_id=manifest.dataset_id,
        feature_columns=FEATURES,
    )
    report = json.loads(
        (output_directory / "earnings-discovery-v1.report.json").read_text("utf-8")
    )
    assert report["point_in_time_data"] is True
    assert len(report["fold_metrics"]) == 2
    for fold in report["fold_metrics"]:
        assert fold["fit_error"] is None
        assert fold["baseline_evaluated_event_count"] == fold[
            "candidate_evaluated_event_count"
        ]
        assert fold["train_support"]["upside_tail_events"] >= 8
        assert fold["train_support"]["downside_tail_events"] >= 8
        assert "logistic_absolute_threshold_brier" in fold
        assert "logistic_downside_tail_log_loss" in fold
        assert "quantile_absolute_gap_interval_coverage" in fold
    assert {row["candidate"] for row in report["calibration"]} == {
        "logistic_absolute_threshold",
        "logistic_downside_tail",
        "hist_gradient_boosting_absolute_threshold",
    }
    slices = report["failure_analysis"]["candidate_slices"]
    assert set(slices["quantile_absolute_gap"]) == {
        "ticker", "industry", "year", "volatility_regime", "release_timing",
    }
    assert len(record.artifact_hashes) == len(CANDIDATES) * 2
    quantile_aggregate = report["aggregate_metrics"]["quantile_absolute_gap"]
    assert set(quantile_aggregate["pinball_loss"]) == {"0.1", "0.5", "0.9"}
    assert quantile_aggregate["interval_coverage"] is not None
    assert quantile_aggregate["confirmation_sample_gate"]["passes"] is True
    assert "Power analysis" in quantile_aggregate["confirmation_sample_gate"][
        "sample_justification"
    ]
    assert report["production_authoritative"] is False

    bundles = {}
    component_hashes = {}
    spec = _spec()
    for candidate in CANDIDATES:
        manifest_hash = record.artifact_hashes[f"{candidate}.manifest"]
        component_hashes[candidate] = record.artifact_hashes[f"{candidate}.artifact"]
        model_manifest = load_model_manifest(
            directory=output_directory,
            filename=f"{spec.experiment_id}.{candidate}.manifest.json",
            model_id=f"{spec.experiment_id}.{candidate}",
            model_version=spec.spec_hash,
            expected_manifest_hash=manifest_hash,
        )
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Setting the shape on a NumPy array has been deprecated.*",
                category=DeprecationWarning,
            )
            bundles[candidate] = load_model_artifact(
                model_manifest,
                directory=output_directory,
                filename=f"{spec.experiment_id}.{candidate}.joblib",
            )
    feature_frame, _ = _fixture_frames()
    event = feature_frame.iloc[0].to_dict()
    forecast = build_typed_forecast(
        spec,
        event,
        bundles,
        component_hashes,
        target_available_at="2024-01-04T14:30:00+00:00",
        baseline_median_absolute_gap_pct=7.0,
        event_support={"distinct_events": 300, "distinct_tickers": 2},
        calibration_status="experimental",
        evidence_status="exploratory",
    )
    assert forecast.available
    assert forecast.production_authoritative is False
    assert forecast.absolute_gap_interval_pct[0] >= 0
    assert forecast.to_dict()["production_authoritative"] is False


def test_same_event_date_is_never_split_across_fold_boundaries(tmp_path):
    dataset_directory = tmp_path / "dataset"
    output_directory = tmp_path / "output"
    manifest = _build_point_in_time_dataset(dataset_directory)
    run_experiment(
        _spec(experiment_id="event-grouping-v1"),
        dataset_directory,
        output_directory,
        "0" * 40,
        dataset_id=manifest.dataset_id,
        feature_columns=FEATURES,
    )
    report = json.loads((output_directory / "event-grouping-v1.report.json").read_text())
    for fold in report["split_summary"]:
        # Two tickers report on every date; a row-level split could produce odd counts.
        assert fold["validation_row_count"] % 2 == 0


def test_thin_first_fold_reports_fit_refusal_not_a_model(tmp_path):
    features, labels = _fixture_frames(n_dates=24)
    manifest = build_dataset_manifest(
        features_df=features,
        labels_df=labels,
        dataset_id="thin-earnings",
        created_at="2026-07-31T00:00:00+00:00",
        task="earnings_gap_forecast",
        feature_set_version="earnings-fs-v1",
        label_version="earnings-gap-v1",
        source_descriptions=("thin synthetic fixture",),
        point_in_time_data=False,
        universe_definition="earnings-fixture-v1",
        entry_timing="overnight_gap",
        target_horizon_sessions=1,
        embargo_sessions=1,
        dropped_label_row_count=0,
        transaction_cost_bps=0.0,
        tax_assumptions="none",
        git_commit="0" * 40,
        benchmark="QQQ",
    )
    save_dataset(features, labels, manifest, directory=tmp_path / "dataset")
    run_experiment(
        _spec(experiment_id="thin-v1"),
        tmp_path / "dataset",
        tmp_path / "output",
        "0" * 40,
        dataset_id=manifest.dataset_id,
        feature_columns=FEATURES,
    )
    report = json.loads((tmp_path / "output" / "thin-v1.report.json").read_text())
    assert all(fold["fit_error"] for fold in report["fold_metrics"])
    assert report["verdict"] == "rejected"
    assert not record_artifacts(tmp_path / "output", "thin-v1")


def record_artifacts(directory: Path, experiment_id: str) -> list[Path]:
    return list(directory.glob(f"{experiment_id}.*.joblib"))


def test_failure_slices_report_the_count_the_metric_actually_scored():
    """A slice metric must publish its own denominator.

    brier_score()/mean_absolute_error() drop non-finite pairs, so a slice
    the model mostly FAILED to predict would otherwise display a strong
    score beside the full event_count -- the score improving precisely as
    coverage got worse. ml/monitoring_reports.py's slice reporting already
    publishes row_count alongside its sufficiency verdict; this one only
    reported the raw size.
    """
    from ml.earnings_experiments import _slice_metrics

    # Ten events in one slice; the model produced a usable probability for
    # only three of them, and those three are the easy ones.
    frame = pd.DataFrame(
        {
            "ticker": ["AAA"] * 10,
            "industry": ["tech"] * 10,
            "year": ["2026"] * 10,
            "volatility_regime": ["low"] * 10,
            "release_timing": ["after_close"] * 10,
            "actual_downside_tail": [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0],
            "prediction_logistic_downside_tail": [
                0.9, 0.1, np.nan, np.nan, np.nan,
                np.nan, np.nan, np.nan, np.nan, 0.1,
            ],
        }
    )

    slices = _slice_metrics(frame, "logistic_downside_tail")
    bucket = slices["ticker"]["AAA"]

    assert bucket["event_count"] == 10
    assert bucket["scored_event_count"] == 3, (
        "the metric scored three pairs; reporting only event_count=10 beside "
        "it overstates the evidence sevenfold"
    )
    assert bucket["primary_metric"] is not None
    assert bucket["scored_event_count"] < bucket["event_count"]


def test_fully_scored_slice_reports_equal_counts():
    """Guards against 'fixing' the above with a constant."""
    from ml.earnings_experiments import _slice_metrics

    frame = pd.DataFrame(
        {
            "ticker": ["BBB"] * 4,
            "industry": ["tech"] * 4,
            "year": ["2026"] * 4,
            "volatility_regime": ["low"] * 4,
            "release_timing": ["after_close"] * 4,
            "actual_downside_tail": [1.0, 0.0, 1.0, 0.0],
            "prediction_logistic_downside_tail": [0.8, 0.2, 0.7, 0.3],
        }
    )
    bucket = _slice_metrics(frame, "logistic_downside_tail")["ticker"]["BBB"]
    assert bucket["event_count"] == bucket["scored_event_count"] == 4


# --------------------------------------------------------------------------
# FCS-002: a metric's denominator must be the observations it actually scored.
#
# FPS-004 fixed exactly this in `_slice_metrics` and added
# `ml.evaluation.usable_pair_count()` for it. `_classification_metrics` was
# never brought along: `calibration_error` summed bin counts (which
# `calibration_curve` builds from finite pairs only) and divided by
# `len(actual)` (every row), so the reported error shrank toward zero as
# coverage got worse -- the same direction FPS-004 named. precision/recall
# additionally scored a NaN probability as a confident negative, because
# `NaN >= threshold` is False.
# --------------------------------------------------------------------------

def _classification_metrics_for(actual, probability, *, threshold=0.5, bins=10):
    from ml.earnings_experiments import _classification_metrics

    return _classification_metrics(
        np.asarray(actual, dtype=float),
        np.asarray(probability, dtype=float),
        threshold=threshold,
        bins=bins,
    )


def test_calibration_error_denominator_is_the_scored_events_not_every_row():
    """Four scored predictions must give the same error however many NaNs sit beside them."""
    actual = [1.0, 0.0, 1.0, 0.0]
    probability = [0.9, 0.1, 0.8, 0.2]
    baseline = _classification_metrics_for(actual, probability)["calibration_error"]

    for padding in (6, 16, 36):
        padded_actual = actual + [0.0] * padding
        padded_probability = probability + [float("nan")] * padding
        metrics = _classification_metrics_for(padded_actual, padded_probability)
        assert metrics["calibration_error"] == pytest.approx(baseline), padding
        assert metrics["scored_event_count"] == 4
        assert metrics["event_count"] == 4 + padding


def test_classification_metrics_publish_both_counts():
    metrics = _classification_metrics_for(
        [1.0, 0.0, 1.0], [0.9, 0.1, float("nan")]
    )
    assert metrics["event_count"] == 3
    assert metrics["scored_event_count"] == 2


def test_precision_and_recall_ignore_unscored_events():
    """A missing probability is not a confident negative prediction.

    `NaN >= threshold` is False, so an unscored event used to land in the
    recall denominator as a miss -- penalising the model for events it
    explicitly declined to predict, while the Brier score for those same
    events was dropped.
    """
    actual = [1.0, 1.0]
    scored_only = _classification_metrics_for(actual, [0.9, 0.9])
    with_unscored = _classification_metrics_for(
        actual + [1.0, 1.0], [0.9, 0.9, float("nan"), float("nan")]
    )
    assert scored_only["recall"] == 1.0
    assert with_unscored["recall"] == 1.0
    assert with_unscored["scored_event_count"] == 2
    assert with_unscored["event_count"] == 4


def test_a_fold_publishes_the_scored_event_count_beside_its_raw_count():
    """`candidate_evaluated_event_count` is a raw len(); its scored twin must exist."""
    import inspect

    from ml import earnings_experiments

    source = inspect.getsource(earnings_experiments)
    assert "candidate_evaluated_event_count" in source
    assert "candidate_scored_event_count" in source, (
        "a raw evaluated-event count must be published beside the count the "
        "metrics actually scored (FPS-004 / FCS-002)"
    )
