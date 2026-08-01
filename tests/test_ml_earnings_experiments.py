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
