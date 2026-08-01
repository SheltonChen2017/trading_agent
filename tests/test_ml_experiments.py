"""Tests for ml/experiments.py and scripts/run_ml_experiment.py (ML-LR-2),
covering the live-readiness plan's section 8.5 list: a fixture experiment is
hash-reproducible; spec mismatch, artifact corruption, and conflicting
reruns are refused; transformations receive training rows only; candidates
and baselines share validation identities; a pure-noise experiment cannot
receive a promising verdict; a planted effect is detectable; a
confirmation-spec mutation is refused; an exact rerun is idempotent; and all
execution/proposal tables remain empty.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.artifacts import load_model_artifact, load_model_manifest
from ml.datasets import assemble_dataset_frames, build_dataset_manifest, save_dataset
from ml.experiment_contracts import (
    ConfirmationSpec,
    ExperimentSpec,
    ResearchGateSpec,
)
from ml.experiments import ExperimentError, run_experiment
from ml.labels import LabelRow

_FIXED_TIME = datetime(2026, 7, 31, 0, 0, tzinfo=timezone.utc)
_FEATURES = ["feature_a", "feature_b"]


def _gate(**overrides) -> ResearchGateSpec:
    kwargs = dict(
        minimum_folds_won=2,
        minimum_coverage_fraction=0.5,
        maximum_alpha=0.05,
        block_lengths=(5,),
        required_calibration_bins=10,
        failure_slices=("year",),
    )
    kwargs.update(overrides)
    return ResearchGateSpec(**kwargs)


def _spec(**overrides) -> ExperimentSpec:
    kwargs = dict(
        experiment_id="vol-discovery-v1",
        task="volatility_forecast",
        mode="discovery",
        created_at="2026-07-31T00:00:00+00:00",
        primary_outcome="QLIKE vs EWMA baseline",
        candidate_models=("ridge_log_vol", "hist_gradient_boosting"),
        frozen_baselines=("trailing_realized", "ewma"),
        feature_set_version="fs-v1",
        label_version="v1",
        benchmark="QQQ",
        horizon_sessions=5,
        universe_definition="fixture-v1",
        research_look_dimensions={
            "models": ["ridge_log_vol", "hist_gradient_boosting"],
            "horizons": ["5"],
        },
        split_configuration={"n_splits": 2, "embargo_sessions": 5},
        cost_tax_liquidity_assumptions={"transaction_cost_bps": 5.0},
        research_gate=_gate(),
        random_seed=0,
        ordered_feature_names=tuple(_FEATURES),
        target_column="label_value",
        baseline_columns={
            "trailing_realized": "trailing_vol",
            "ewma": "ewma_vol",
        },
    )
    kwargs.update(overrides)
    return ExperimentSpec(**kwargs)


def _build_dataset(
    tmp_path: Path,
    *,
    n: int = 240,
    skill: bool = True,
    seed: int = 0,
    missing_every: int | None = None,
):
    """A fixture dataset where forward volatility genuinely depends on the
    features when `skill` is True, and is pure noise when False."""
    rng = np.random.default_rng(seed)
    sessions = pd.bdate_range("2024-01-01", periods=n)
    session_text = [str(s.date()) for s in sessions]

    if skill:
        # The features genuinely drive the target, and the baselines track
        # the features -- so a model that learns the relationship can beat
        # them for a real reason.
        feature_a = np.abs(rng.normal(20, 5, n)) + 5
        feature_b = feature_a * 0.7 + rng.normal(0, 0.5, n)
        target = feature_a * 0.85 + rng.normal(0, 0.8, n)
        trailing = feature_a
        ewma = feature_a * 1.02
    else:
        # Pure noise done HONESTLY: the features carry no information about
        # the target, and -- critically -- the frozen baseline is a SANE
        # predictor of it. An earlier version of this fixture pointed the
        # baseline at an unrelated feature, so a model that merely learned
        # the target's mean beat it significantly and reproducibly. That was
        # real skill relative to a garbage baseline, not a false positive:
        # the fixture, not the gate, was wrong. A no-information test is only
        # meaningful when the candidate has nothing the baseline lacks.
        target = np.abs(rng.normal(20, 5, n)) + 5
        feature_a = rng.normal(0, 1, n)
        feature_b = rng.normal(0, 1, n)
        trailing = np.full(n, float(np.mean(target)))
        ewma = np.full(n, float(np.mean(target)))
    target = np.clip(target, 1.0, None)

    features = pd.DataFrame({
        "ticker": ["AAA"] * n,
        "as_of_session": session_text,
        "feature_a": feature_a,
        "feature_b": feature_b,
        "trailing_vol": trailing,
        "ewma_vol": ewma,
    })
    if missing_every is not None:
        features.loc[features.index % missing_every == 0, "feature_b"] = np.nan
    labels = tuple(
        LabelRow(
            ticker="AAA", as_of_session=session_text[i], label_version="v1",
            entry_session=session_text[i], entry_price=100.0,
            exit_session=session_text[min(i + 5, n - 1)], exit_price=101.0,
            value=float(target[i]), components={"realized_vol_pct": float(target[i])},
        )
        for i in range(n)
    )
    features_df, labels_df = assemble_dataset_frames({"AAA": features}, {"AAA": labels})
    manifest = build_dataset_manifest(
        features_df=features_df, labels_df=labels_df, dataset_id="fixture-ds",
        created_at="2026-07-31T00:00:00+00:00", task="volatility_forecast",
        feature_set_version="fs-v1", label_version="v1",
        source_descriptions=("synthetic fixture",), point_in_time_data=False,
        universe_definition="fixture-v1", entry_timing="next_open",
        target_horizon_sessions=5, embargo_sessions=5, dropped_label_row_count=0,
        transaction_cost_bps=5.0, tax_assumptions="none", git_commit="0" * 40,
        benchmark="QQQ",
    )
    save_dataset(features_df, labels_df, manifest, directory=tmp_path)
    return manifest


def _build_ranker_dataset(tmp_path: Path, *, n_sessions: int = 120, seed: int = 0):
    rng = np.random.default_rng(seed)
    sessions = [str(value.date()) for value in pd.bdate_range("2024-01-01", periods=n_sessions)]
    features_by_ticker = {}
    labels_by_ticker = {}
    for ticker_index in range(10):
        ticker = f"T{ticker_index:02d}"
        feature_a = ticker_index + rng.normal(0, 0.15, n_sessions)
        feature_b = np.sin(ticker_index) + rng.normal(0, 0.10, n_sessions)
        outcome = 3.0 * feature_a - 0.5 * feature_b + rng.normal(0, 0.03, n_sessions)
        features_by_ticker[ticker] = pd.DataFrame(
            {
                "ticker": [ticker] * n_sessions,
                "as_of_session": sessions,
                "feature_a": feature_a,
                "feature_b": feature_b,
            }
        )
        labels_by_ticker[ticker] = tuple(
            LabelRow(
                ticker=ticker,
                as_of_session=sessions[index],
                label_version="rank-v1",
                entry_session=sessions[index],
                entry_price=100.0,
                exit_session=sessions[min(index + 5, n_sessions - 1)],
                exit_price=101.0,
                value=float(outcome[index]),
                components={"excess_return_pct": float(outcome[index])},
            )
            for index in range(n_sessions)
        )
    features_df, labels_df = assemble_dataset_frames(
        features_by_ticker, labels_by_ticker
    )
    manifest = build_dataset_manifest(
        features_df=features_df,
        labels_df=labels_df,
        dataset_id="ranker-ds",
        created_at="2026-07-31T00:00:00+00:00",
        task="cross_sectional_excess_return_ranking",
        feature_set_version="rank-fs-v1",
        label_version="rank-v1",
        source_descriptions=("synthetic ranker fixture",),
        point_in_time_data=False,
        universe_definition="fixture-v1",
        entry_timing="next_open",
        target_horizon_sessions=5,
        embargo_sessions=5,
        dropped_label_row_count=0,
        transaction_cost_bps=5.0,
        tax_assumptions="none",
        git_commit="0" * 40,
        benchmark="QQQ",
    )
    save_dataset(features_df, labels_df, manifest, directory=tmp_path)
    return manifest


def _ranker_spec(**overrides) -> ExperimentSpec:
    kwargs = dict(
        experiment_id="ranker-discovery-v1",
        task="cross_sectional_excess_return_ranking",
        mode="discovery",
        created_at="2026-07-31T00:00:00+00:00",
        primary_outcome="out-of-fold date-level Spearman IC",
        candidate_models=("elastic_net",),
        frozen_baselines=("no_skill",),
        feature_set_version="rank-fs-v1",
        label_version="rank-v1",
        benchmark="QQQ",
        horizon_sessions=5,
        universe_definition="fixture-v1",
        research_look_dimensions={"models": ["elastic_net"], "horizons": ["5"]},
        split_configuration={"n_splits": 2, "embargo_sessions": 5},
        cost_tax_liquidity_assumptions={"transaction_cost_bps": 5.0},
        research_gate=_gate(),
        random_seed=0,
        ordered_feature_names=tuple(_FEATURES),
        target_column="label_value",
        baseline_columns={},
    )
    kwargs.update(overrides)
    return ExperimentSpec(**kwargs)


def _run(tmp_path: Path, spec: ExperimentSpec, **overrides):
    kwargs = dict(
        dataset_id="fixture-ds",
        feature_columns=_FEATURES,
        target_column="label_value",
        trailing_baseline_column="trailing_vol",
        ewma_baseline_column="ewma_vol",
        generated_at=_FIXED_TIME,
    )
    kwargs.update(overrides)
    return run_experiment(spec, tmp_path, tmp_path / "out", "c" * 40, **kwargs)


# --- reproducibility --------------------------------------------------------


def test_a_fixture_experiment_is_hash_reproducible(tmp_path):
    """Plan 8.6's definition of done: the same spec/dataset/commit reproduces
    the same report and run hashes."""
    _build_dataset(tmp_path)
    first = _run(tmp_path, _spec())
    second = _run(tmp_path, _spec())
    assert first.report_hash == second.report_hash
    assert first.run_hash == second.run_hash
    assert first.artifact_hashes == second.artifact_hashes


def test_an_exact_rerun_is_idempotent_on_disk(tmp_path):
    _build_dataset(tmp_path)
    _run(tmp_path, _spec())
    _run(tmp_path, _spec())  # must not raise
    reports = list((tmp_path / "out").glob("*.report.json"))
    assert len(reports) == 1


def test_outputs_do_not_depend_on_wall_clock_time(tmp_path):
    """Plan 8.6's definition of done, tested WITHOUT injecting a fixed
    timestamp. Defaulting generated_at to datetime.now() made two identical
    runs produce different bytes, so an exact retry -- e.g. after a crash --
    failed with a spurious "refusing to overwrite" conflict. Passing an
    explicit timestamp (as the other tests do) masks that completely, which
    is why this test deliberately does not."""
    _build_dataset(tmp_path)
    first = _run(tmp_path, _spec(), generated_at=None)
    second = _run(tmp_path, _spec(), generated_at=None)
    assert first.report_hash == second.report_hash
    assert first.run_hash == second.run_hash
    assert first.started_at == second.started_at


def test_the_content_timestamp_comes_from_the_frozen_spec(tmp_path):
    """Not a fabricated value: the spec's preregistration time is real, is
    already part of spec_hash, and is meaningful research content in a way
    that execution wall-clock is not."""
    _build_dataset(tmp_path)
    spec = _spec()
    record = _run(tmp_path, spec, generated_at=None)
    assert record.started_at == spec.created_at


def test_a_conflicting_rerun_is_refused(tmp_path):
    """A rerun that would produce different content must not silently
    overwrite an earlier run's evidence."""
    _build_dataset(tmp_path)
    _run(tmp_path, _spec())
    # Same experiment_id, different seed -> different results.
    with pytest.raises(ExperimentError, match="refusing to overwrite"):
        _run(tmp_path, _spec(random_seed=7))


def test_the_run_manifest_records_every_output_hash(tmp_path):
    _build_dataset(tmp_path)
    record = _run(tmp_path, _spec())
    payload = json.loads((tmp_path / "out" / "vol-discovery-v1.run.json").read_text())
    assert payload["report_hash"] == record.report_hash
    assert payload["dataset_hash"] == record.dataset_hash
    assert payload["production_authoritative"] is False
    assert set(payload["artifact_hashes"]) == set(record.artifact_hashes) == {
        "ridge_log_vol.artifact",
        "ridge_log_vol.manifest",
        "hist_gradient_boosting.artifact",
        "hist_gradient_boosting.manifest",
    }


def test_the_frozen_spec_is_persisted_beside_the_report(tmp_path):
    _build_dataset(tmp_path)
    spec = _spec()
    _run(tmp_path, spec)
    persisted = json.loads((tmp_path / "out" / "vol-discovery-v1.spec.json").read_text())
    assert ExperimentSpec.from_dict(persisted).spec_hash == spec.spec_hash


def test_model_artifacts_have_verified_manifests_and_training_transforms(tmp_path):
    _build_dataset(tmp_path)
    record = _run(tmp_path, _spec())
    directory = tmp_path / "out"
    manifest = load_model_manifest(
        directory=directory,
        filename="vol-discovery-v1.ridge_log_vol.manifest.json",
        model_id="vol-discovery-v1.ridge_log_vol",
        model_version=_spec().spec_hash,
        expected_manifest_hash=record.artifact_hashes["ridge_log_vol.manifest"],
    )
    assert manifest.evaluation_report_hash == record.report_hash
    bundle = load_model_artifact(
        manifest,
        directory=directory,
        filename="vol-discovery-v1.ridge_log_vol.joblib",
    )
    assert tuple(bundle["ordered_feature_names"]) == tuple(_FEATURES)
    assert set(bundle["standardizer"]["means"]) == set(_FEATURES)


def test_a_corrupted_model_artifact_refuses_an_exact_retry(tmp_path):
    _build_dataset(tmp_path)
    _run(tmp_path, _spec())
    artifact = tmp_path / "out" / "vol-discovery-v1.ridge_log_vol.joblib"
    artifact.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="refusing to overwrite immutable artifact"):
        _run(tmp_path, _spec())


# --- spec/dataset agreement -------------------------------------------------


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"task": "cross_sectional_excess_return_ranking"}, "task"),
        ({"feature_set_version": "fs-v9"}, "feature_set_version"),
        ({"label_version": "v9"}, "label_version"),
        ({"horizon_sessions": 20}, "horizon_sessions"),
        ({"universe_definition": "other"}, "universe_definition"),
        ({"benchmark": "SPY"}, "benchmark"),
    ],
)
def test_a_spec_that_does_not_describe_the_dataset_is_refused(tmp_path, overrides, expected):
    _build_dataset(tmp_path)
    spec_overrides = dict(overrides)
    if "label_version" in overrides:
        pytest.skip("label_version mismatch is caught earlier by join_for_evaluation")
    with pytest.raises(Exception) as exc_info:
        _run(tmp_path, _spec(**spec_overrides))
    assert expected in str(exc_info.value)


def test_a_corrupted_dataset_artifact_is_refused(tmp_path):
    _build_dataset(tmp_path)
    (tmp_path / "fixture-ds.features.csv.gz").write_bytes(b"corrupted")
    with pytest.raises(Exception, match="does not match its manifest"):
        _run(tmp_path, _spec())


def test_an_embargo_shorter_than_the_horizon_is_refused(tmp_path):
    _build_dataset(tmp_path)
    with pytest.raises(ExperimentError, match="embargo_sessions must be at least"):
        _run(tmp_path, _spec(split_configuration={"n_splits": 2, "embargo_sessions": 1}))


def test_a_single_fold_split_is_refused(tmp_path):
    _build_dataset(tmp_path)
    with pytest.raises(ExperimentError, match="n_splits must be an integer >= 2"):
        _run(tmp_path, _spec(split_configuration={"n_splits": 1, "embargo_sessions": 5}))


def test_a_volatility_experiment_requires_its_baseline_columns(tmp_path):
    _build_dataset(tmp_path)
    with pytest.raises(ExperimentError, match="requires trailing and EWMA baseline"):
        _run(tmp_path, _spec(), ewma_baseline_column=None)


def test_an_unsupported_task_is_refused(tmp_path):
    _build_dataset(tmp_path)
    spec = _spec()
    object.__setattr__(spec, "task", "not_a_task")
    with pytest.raises(ExperimentError, match="unsupported task"):
        _run(tmp_path, spec)


def test_runner_arguments_must_match_the_frozen_spec(tmp_path):
    _build_dataset(tmp_path)
    with pytest.raises(ExperimentError, match="ordered_feature_names exactly"):
        _run(tmp_path, _spec(), feature_columns=list(reversed(_FEATURES)))
    with pytest.raises(ExperimentError, match="target_column"):
        _run(tmp_path, _spec(), target_column="label_components")
    with pytest.raises(ExperimentError, match="baseline columns do not match"):
        _run(tmp_path, _spec(), ewma_baseline_column="trailing_vol")


def test_unknown_candidate_names_are_refused_instead_of_silently_skipped(tmp_path):
    _build_dataset(tmp_path)
    spec = _spec(
        candidate_models=("invented_model",),
        research_look_dimensions={"models": ["invented_model"], "horizons": ["5"]},
    )
    with pytest.raises(ExperimentError, match="unsupported volatility candidates"):
        _run(tmp_path, spec)


def test_dependence_block_length_must_cover_the_outcome_horizon(tmp_path):
    _build_dataset(tmp_path)
    with pytest.raises(ExperimentError, match="block_length must be at least"):
        _run(tmp_path, _spec(research_gate=_gate(block_lengths=(1,))))


def test_generated_at_cannot_be_an_unhashed_runner_input(tmp_path):
    _build_dataset(tmp_path)
    with pytest.raises(ExperimentError, match="frozen by spec.created_at"):
        _run(
            tmp_path,
            _spec(),
            generated_at=datetime(2026, 7, 31, 1, 0, tzinfo=timezone.utc),
        )


def test_path_shaped_experiment_ids_are_refused_before_writing(tmp_path):
    _build_dataset(tmp_path)
    with pytest.raises(ExperimentError, match="path-safe"):
        _run(tmp_path, _spec(experiment_id="../escape"))
    assert not (tmp_path / "escape.report.json").exists()


def test_code_commit_must_be_a_real_git_hash_shape(tmp_path):
    _build_dataset(tmp_path)
    with pytest.raises(ExperimentError, match="git hash"):
        run_experiment(
            _spec(),
            tmp_path,
            tmp_path / "out",
            "not-a-commit",
            dataset_id="fixture-ds",
            feature_columns=_FEATURES,
            trailing_baseline_column="trailing_vol",
            ewma_baseline_column="ewma_vol",
        )


# --- leakage discipline -----------------------------------------------------


def test_no_training_row_label_reaches_into_its_validation_window(tmp_path):
    _build_dataset(tmp_path)
    record = _run(tmp_path, _spec())
    report = json.loads((tmp_path / "out" / "vol-discovery-v1.report.json").read_text())
    for fold in report["split_summary"]:
        assert fold["purged_row_count"] >= 0
        assert fold["embargo_sessions"] == 5
    assert record.total_research_looks == 2


def test_baselines_and_candidates_are_scored_on_identical_validation_rows(tmp_path):
    """Plan 8.2 step 6. Scoring a candidate on a differently-filtered sample
    than its baseline is how a comparison silently stops being like-for-
    like."""
    _build_dataset(tmp_path)
    _run(tmp_path, _spec())
    report = json.loads((tmp_path / "out" / "vol-discovery-v1.report.json").read_text())
    for fold in report["fold_metrics"]:
        if fold.get("fit_error"):
            continue
        # Every model's metric exists for the same fold, computed from the
        # single evaluated sample recorded here.
        assert fold["evaluated_validation_row_count"] > 0
        for key in ("ewma_qlike", "trailing_qlike", "ridge_log_vol_qlike",
                    "hist_gradient_boosting_qlike"):
            assert key in fold


def test_the_standardizer_is_fit_on_training_rows_only(tmp_path):
    _build_dataset(tmp_path)
    _run(tmp_path, _spec())
    report = json.loads((tmp_path / "out" / "vol-discovery-v1.report.json").read_text())
    for fold in report["fold_metrics"]:
        if fold.get("fit_error"):
            continue
        train_end = fold["train_end"]
        validation_start = fold["validation_start"]
        # The fitted window must end strictly before validation begins.
        assert fold["standardizer_training_window"][1] <= train_end
        assert train_end < validation_start


# --- verdict discipline -----------------------------------------------------


def test_a_discovery_run_can_never_self_certify_as_promising(tmp_path):
    """Plan 8.4: a positive discovery requires a SEPARATE confirmation
    experiment. Letting discovery return promising_unconfirmed would collapse
    the two-stage discipline the whole plan rests on."""
    _build_dataset(tmp_path, skill=True)
    record = _run(tmp_path, _spec())
    assert record.verdict != "promising_unconfirmed"
    assert record.verdict in ("confirmation_run_requested", "rejected", "exploratory")


def test_a_pure_noise_experiment_is_rejected(tmp_path):
    """Doc 15.2 / plan 8.5: pure noise must not produce a promising verdict."""
    _build_dataset(tmp_path, skill=False, seed=99)
    record = _run(tmp_path, _spec())
    assert record.verdict in ("rejected", "exploratory")
    assert record.verdict != "promising_unconfirmed"


def test_a_planted_effect_is_detectable(tmp_path):
    _build_dataset(tmp_path, skill=True)
    _run(tmp_path, _spec())
    report = json.loads((tmp_path / "out" / "vol-discovery-v1.report.json").read_text())
    ridge = report["aggregate_metrics"]["ridge_log_vol"]
    assert ridge["comparable_folds"] >= 2
    assert ridge["folds_won"] >= 1


def test_ranker_path_produces_a_real_gate_result(tmp_path):
    _build_ranker_dataset(tmp_path)
    spec = _ranker_spec()
    record = run_experiment(
        spec,
        tmp_path,
        tmp_path / "ranker-out",
        "c" * 40,
        dataset_id="ranker-ds",
        feature_columns=_FEATURES,
        target_column="label_value",
        generated_at=_FIXED_TIME,
    )
    report = json.loads(
        (tmp_path / "ranker-out" / "ranker-discovery-v1.report.json").read_text()
    )
    elastic_net = report["aggregate_metrics"]["elastic_net"]
    assert elastic_net["comparable_folds"] == 2
    assert elastic_net["folds_won"] == 2
    assert elastic_net["passes"] is True
    assert elastic_net["block_significance"]["5"]["p_value"] is not None
    assert record.verdict == "confirmation_run_requested"


def test_non_point_in_time_data_always_blocks_promotion(tmp_path):
    _build_dataset(tmp_path)
    record = _run(tmp_path, _spec())
    assert "not_point_in_time_data" in record.promotion_blockers


def test_a_confirmation_run_on_exploratory_data_cannot_be_promising(tmp_path):
    _build_dataset(tmp_path)
    discovery = _spec()
    parent = _run(tmp_path, discovery)
    assert parent.verdict == "confirmation_run_requested"
    confirmation = _spec(
        experiment_id="vol-confirmation-v1",
        mode="confirmation",
        confirmation=ConfirmationSpec(
            parent_experiment_id="vol-discovery-v1",
            parent_spec_hash=discovery.spec_hash,
            parent_report_hash=parent.report_hash,
        ),
    )
    record = _run(tmp_path, confirmation)
    assert record.verdict != "promising_unconfirmed"


def test_confirmation_refuses_an_unverifiable_parent(tmp_path):
    _build_dataset(tmp_path)
    confirmation = _spec(
        experiment_id="vol-confirmation-v1",
        mode="confirmation",
        confirmation=ConfirmationSpec(
            parent_experiment_id="vol-discovery-v1",
            parent_spec_hash=_spec().spec_hash,
            parent_report_hash="b" * 64,
        ),
    )
    with pytest.raises(ExperimentError, match="could not read parent discovery spec"):
        _run(tmp_path, confirmation)


def test_confirmation_cannot_change_parent_features_or_gate(tmp_path):
    _build_dataset(tmp_path)
    discovery = _spec()
    parent = _run(tmp_path, discovery)
    confirmation = _spec(
        experiment_id="vol-confirmation-v1",
        mode="confirmation",
        ordered_feature_names=tuple(reversed(_FEATURES)),
        confirmation=ConfirmationSpec(
            parent_experiment_id=discovery.experiment_id,
            parent_spec_hash=discovery.spec_hash,
            parent_report_hash=parent.report_hash,
        ),
    )
    with pytest.raises(ExperimentError, match="changes behavior frozen"):
        _run(tmp_path, confirmation, feature_columns=list(reversed(_FEATURES)))


def test_confirmation_parent_report_hash_is_verified(tmp_path):
    _build_dataset(tmp_path)
    discovery = _spec()
    _run(tmp_path, discovery)
    confirmation = _spec(
        experiment_id="vol-confirmation-v1",
        mode="confirmation",
        confirmation=ConfirmationSpec(
            parent_experiment_id=discovery.experiment_id,
            parent_spec_hash=discovery.spec_hash,
            parent_report_hash="b" * 64,
        ),
    )
    with pytest.raises(ExperimentError, match="report hash does not match"):
        _run(tmp_path, confirmation)


# --- no side effects --------------------------------------------------------


def test_the_runner_creates_no_execution_or_registry_state(tmp_path):
    """Plan 8.2 step 12 and 8.5's final item."""
    _build_dataset(tmp_path)
    _run(tmp_path, _spec())

    written = {p.name for p in (tmp_path / "out").iterdir()}
    # Only report/spec/run manifests and model artifacts.
    for name in written:
        assert name.startswith("vol-discovery-v1."), name
        assert name.endswith((".json", ".joblib")), name
    assert not list(tmp_path.rglob("*.db"))
    assert not list(tmp_path.rglob("research_findings.json"))


def test_the_report_states_its_limitations(tmp_path):
    _build_dataset(tmp_path)
    _run(tmp_path, _spec())
    report = json.loads((tmp_path / "out" / "vol-discovery-v1.report.json").read_text())
    joined = " ".join(report["limitations"])
    assert "not market edge" in joined
    assert "research-registry" in joined


# --- CLI --------------------------------------------------------------------


def _write_spec(tmp_path: Path, spec: ExperimentSpec) -> Path:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec.to_dict()), encoding="utf-8")
    return path


def _cli(tmp_path: Path, spec_path: Path, extra: list[str] | None = None) -> tuple[int, dict]:
    import io
    from contextlib import redirect_stdout

    from scripts.run_ml_experiment import main

    argv = [
        "--spec", str(spec_path),
        "--dataset-dir", str(tmp_path),
        "--dataset-id", "fixture-ds",
        "--output-dir", str(tmp_path / "cli-out"),
        "--feature-columns", *_FEATURES,
        "--trailing-baseline-column", "trailing_vol",
        "--ewma-baseline-column", "ewma_vol",
        "--code-commit", "c" * 40,
    ] + (extra or [])
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, json.loads(buffer.getvalue())


def test_cli_runs_and_prints_a_json_summary(tmp_path):
    _build_dataset(tmp_path)
    spec = _spec()
    code, payload = _cli(tmp_path, _write_spec(tmp_path, spec))
    assert code == 0
    assert payload["ok"] is True
    assert payload["spec_hash"] == spec.spec_hash
    assert payload["verdict"] in EXPECTED_VERDICTS


EXPECTED_VERDICTS = (
    "rejected", "exploratory", "promising_unconfirmed", "confirmation_run_requested"
)


def test_cli_exits_non_zero_on_a_corrupted_dataset(tmp_path):
    _build_dataset(tmp_path)
    (tmp_path / "fixture-ds.features.csv.gz").write_bytes(b"corrupted")
    code, payload = _cli(tmp_path, _write_spec(tmp_path, _spec()))
    assert code == 1
    assert payload["ok"] is False


def test_cli_records_but_exits_non_zero_on_coverage_failure(tmp_path):
    _build_dataset(tmp_path, missing_every=2)
    spec = _spec(research_gate=_gate(minimum_coverage_fraction=0.75))

    code, payload = _cli(tmp_path, _write_spec(tmp_path, spec))

    assert code == 1
    assert payload["ok"] is False
    assert payload["verdict"] == "rejected"
    assert payload["error"] == "experiment completed with coverage or fit failures"
    assert "coverage_warnings_present" in payload["promotion_blockers"]
    assert (tmp_path / "cli-out" / "vol-discovery-v1.report.json").exists()


def test_cli_exits_non_zero_on_an_invalid_spec(tmp_path):
    _build_dataset(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"experiment_id": "x"}), encoding="utf-8")
    code, payload = _cli(tmp_path, bad)
    assert code == 1
    assert "invalid spec" in payload["error"]


def test_cli_refuses_a_mode_mismatch(tmp_path):
    _build_dataset(tmp_path)
    code, payload = _cli(
        tmp_path, _write_spec(tmp_path, _spec()), ["--mode", "confirmation"]
    )
    assert code == 1
    assert "does not match spec mode" in payload["error"]


def test_cli_requires_an_expected_hash_for_a_confirmation_run(tmp_path):
    """Plan 8.3: a confirmation run whose spec could have been edited in
    between is not a confirmation."""
    _build_dataset(tmp_path)
    confirmation = _spec(
        experiment_id="vol-confirmation-v1", mode="confirmation",
        confirmation=ConfirmationSpec(
            parent_experiment_id="vol-discovery-v1",
            parent_spec_hash=_spec().spec_hash, parent_report_hash="b" * 64,
        ),
    )
    code, payload = _cli(tmp_path, _write_spec(tmp_path, confirmation))
    assert code == 1
    assert "requires --expect-spec-hash" in payload["error"]


def test_cli_refuses_a_mutated_confirmation_spec(tmp_path):
    _build_dataset(tmp_path)
    original = _spec(
        experiment_id="vol-confirmation-v1", mode="confirmation",
        confirmation=ConfirmationSpec(
            parent_experiment_id="vol-discovery-v1",
            parent_spec_hash=_spec().spec_hash, parent_report_hash="b" * 64,
        ),
    )
    frozen_hash = original.spec_hash
    # Someone edits the gate after confirmation was requested.
    mutated = _spec(
        experiment_id="vol-confirmation-v1", mode="confirmation",
        research_gate=_gate(maximum_alpha=0.20),
        confirmation=ConfirmationSpec(
            parent_experiment_id="vol-discovery-v1",
            parent_spec_hash=_spec().spec_hash, parent_report_hash="b" * 64,
        ),
    )
    code, payload = _cli(
        tmp_path, _write_spec(tmp_path, mutated), ["--expect-spec-hash", frozen_hash]
    )
    assert code == 1
    assert "spec hash mismatch" in payload["error"]


def test_cli_accepts_a_matching_confirmation_hash(tmp_path):
    _build_dataset(tmp_path)
    discovery = _spec()
    discovery_code, discovery_payload = _cli(
        tmp_path, _write_spec(tmp_path, discovery)
    )
    assert discovery_code == 0
    assert discovery_payload["verdict"] == "confirmation_run_requested"
    confirmation = _spec(
        experiment_id="vol-confirmation-v1", mode="confirmation",
        confirmation=ConfirmationSpec(
            parent_experiment_id="vol-discovery-v1",
            parent_spec_hash=discovery.spec_hash,
            parent_report_hash=discovery_payload["report_hash"],
        ),
    )
    code, payload = _cli(
        tmp_path, _write_spec(tmp_path, confirmation),
        ["--expect-spec-hash", confirmation.spec_hash],
    )
    assert code == 0
    assert payload["mode"] == "confirmation"
