"""ML-LR-2: durable experiment orchestration (live-readiness plan section 8).

Replaces ad hoc function calls with reproducible discovery and confirmation
runs whose inputs, outputs, code, and decisions are all immutable and
hashed.

This is an ORCHESTRATION layer, not a framework (plan 8.2: "It may
coordinate existing functions but must not hide task logic behind a
framework"). Every model fit, metric, split, and significance test below is
an existing function from ml/ or backtest/; this module's job is only to
call them in the one order that preserves the research discipline:

  baselines are fit BEFORE candidates, on identical training rows, and both
  are scored on identical validation rows.

That ordering is not cosmetic. If a candidate is fit first and a baseline
afterwards, it becomes trivially easy -- and invisible in the output -- to
tune the baseline's inputs to lose. Fitting frozen baselines first makes
the comparison honest by construction.

The runner never writes to `assistant/research_findings.json`, the model
registry, proposals, or any execution table (plan 8.2 step 12). It only
writes into the caller-supplied output directory.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from backtest.engine import (
    bonferroni_threshold,
    bootstrap_edge_significance_by_block,
)
from ml.artifacts import save_model_artifact, save_model_manifest
from ml.contracts import ModelManifest
from ml.cross_sectional import (
    block_bootstrap_ic_significance,
    evaluate_ranker_fold,
    fit_elastic_net_ranker,
    fit_gradient_boosted_ranker,
)
from ml.datasets import join_for_evaluation, load_dataset
from ml.evaluation import (
    EvaluationReport,
    beats_baseline_in_multiple_folds,
    date_level_spearman_ic,
)
from ml.experiment_contracts import (
    ExperimentRunRecord,
    ExperimentSpec,
)
from ml.hashing import canonical_json, hash_bytes, hash_payload
from ml.splits import purged_grouped_walk_forward_splits
from ml.transforms import apply_training_standardizer, fit_training_standardizer
from ml.volatility import (
    build_volatility_training_matrix,
    fit_gradient_boosted_volatility,
    fit_log_volatility_regression,
    predict_volatility,
)
from ml.evaluation import mean_absolute_error, qlike_loss

SUPPORTED_TASKS = ("volatility_forecast", "cross_sectional_excess_return_ranking")


class ExperimentError(ValueError):
    """An experiment cannot be run reproducibly as specified."""


def _atomic_write(directory: Path, filename: str, data: bytes) -> Path:
    """Immutable write: an existing byte-identical file is a no-op (so an
    exact rerun is idempotent), a differing one is refused (so a conflicting
    rerun cannot silently overwrite an earlier run's evidence)."""
    import os
    import tempfile

    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / filename
    if destination.exists():
        if destination.read_bytes() == data:
            return destination
        raise ExperimentError(
            f"refusing to overwrite existing experiment output {destination} with "
            "different content; a rerun that changes results must use a new "
            "experiment_id"
        )
    fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=f".{filename}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if destination.exists():
            if destination.read_bytes() == data:
                tmp_path.unlink(missing_ok=True)
                return destination
            raise ExperimentError(
                f"refusing to overwrite existing experiment output {destination}"
            )
        os.replace(tmp_path, destination)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return destination


def _parse_spec_timestamp(spec: ExperimentSpec) -> datetime:
    """The spec's frozen preregistration time, used as the deterministic
    content timestamp for this experiment's outputs."""
    return datetime.fromisoformat(spec.created_at.replace("Z", "+00:00"))


def _verify_spec_against_dataset(spec: ExperimentSpec, manifest: Any) -> None:
    """Plan 8.2 step 2. A spec that does not describe the dataset it is being
    run against produces results attributed to the wrong experiment -- the
    most dangerous kind of reproducibility failure, because nothing looks
    broken."""
    mismatches: list[str] = []
    if spec.task != manifest.task:
        mismatches.append(f"task: spec={spec.task!r} dataset={manifest.task!r}")
    if spec.feature_set_version != manifest.feature_set_version:
        mismatches.append(
            f"feature_set_version: spec={spec.feature_set_version!r} "
            f"dataset={manifest.feature_set_version!r}"
        )
    if spec.label_version != manifest.label_version:
        mismatches.append(
            f"label_version: spec={spec.label_version!r} dataset={manifest.label_version!r}"
        )
    if spec.horizon_sessions != manifest.target_horizon_sessions:
        mismatches.append(
            f"horizon_sessions: spec={spec.horizon_sessions} "
            f"dataset={manifest.target_horizon_sessions}"
        )
    if spec.universe_definition != manifest.universe_definition:
        mismatches.append(
            f"universe_definition: spec={spec.universe_definition!r} "
            f"dataset={manifest.universe_definition!r}"
        )
    if mismatches:
        raise ExperimentError(
            "spec does not match the dataset it was run against: " + "; ".join(mismatches)
        )


def _fold_configuration(spec: ExperimentSpec) -> tuple[int, int]:
    configuration = spec.split_configuration
    n_splits = configuration.get("n_splits")
    embargo = configuration.get("embargo_sessions")
    if not isinstance(n_splits, int) or isinstance(n_splits, bool) or n_splits < 2:
        raise ExperimentError(
            "split_configuration.n_splits must be an integer >= 2; doc 14.1 requires "
            "beating a baseline in more than one untouched fold"
        )
    if not isinstance(embargo, int) or isinstance(embargo, bool) or embargo < 0:
        raise ExperimentError("split_configuration.embargo_sessions must be a non-negative integer")
    if embargo < spec.horizon_sessions:
        raise ExperimentError(
            "split_configuration.embargo_sessions must be at least horizon_sessions; "
            "a shorter embargo leaves overlapping label windows adjacent to validation"
        )
    return n_splits, embargo


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], label: str) -> None:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ExperimentError(f"{label} is missing required column(s): {missing}")


def _run_volatility_task(
    spec: ExperimentSpec,
    joined: pd.DataFrame,
    folds: Sequence[Any],
    *,
    feature_columns: Sequence[str],
    target_column: str,
    trailing_column: str,
    ewma_column: str,
    output_directory: Path,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, Any]]:
    """Fit frozen baselines first, then candidates, on identical rows."""
    fold_metrics: list[dict[str, Any]] = []
    artifact_hashes: dict[str, str] = {}
    # Out-of-fold per-row QLIKE losses, retained by their independent date so
    # aggregate significance is computed across untouched validation rows
    # only (plan 8.2 step 7).
    loss_rows: dict[str, list[pd.DataFrame]] = {}

    for fold in folds:
        train = joined.iloc[list(fold.train_row_indices)]
        validation = joined.iloc[list(fold.validation_row_indices)]

        metrics: dict[str, Any] = {
            "fold_index": fold.fold_index,
            "train_start": fold.train_start,
            "train_end": fold.train_end,
            "validation_start": fold.validation_start,
            "validation_end": fold.validation_end,
            "train_row_count": len(train),
            "validation_row_count": len(validation),
            "purged_row_count": fold.purged_row_count,
            "embargoed_row_count": fold.embargoed_row_count,
        }

        # Build the evaluation sample ONCE so baselines and candidates are
        # scored on byte-identical validation rows (plan 8.2 step 6). Scoring
        # them on differently-filtered samples is the classic way a
        # comparison silently stops being like-for-like.
        columns = list(dict.fromkeys([*feature_columns, target_column, trailing_column, ewma_column]))
        train_sample = train[columns].apply(pd.to_numeric, errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        ).dropna()
        validation_sample = validation[columns].apply(pd.to_numeric, errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        ).dropna()
        metrics["evaluated_validation_row_count"] = len(validation_sample)
        if train_sample.empty or validation_sample.empty:
            metrics["fit_error"] = "no rows survive finite filtering"
            fold_metrics.append(metrics)
            continue

        actual = validation_sample[target_column].to_numpy(dtype=float)
        sessions = joined.loc[validation_sample.index, "as_of_session"]

        # --- frozen baselines FIRST (plan 8.2 step 5) ---------------------
        baseline_losses: np.ndarray | None = None
        for label, column in (("trailing", trailing_column), ("ewma", ewma_column)):
            predicted = validation_sample[column].to_numpy(dtype=float)
            metrics[f"{label}_qlike"] = qlike_loss(actual, predicted)
            metrics[f"{label}_mae"] = mean_absolute_error(actual, predicted)
            if label == "ewma":
                baseline_losses = _pointwise_qlike(actual, predicted)

        # --- transformations fit on TRAINING rows only (step 4) ----------
        standardizer = fit_training_standardizer(
            joined, list(feature_columns),
            train_row_indices=[
                index for index in fold.train_row_indices
                if index in set(train_sample.index)
            ] or list(fold.train_row_indices),
        )
        metrics["standardizer_training_rows"] = standardizer.training_row_count
        metrics["standardizer_training_window"] = [
            standardizer.training_start, standardizer.training_end
        ]

        x_train = train_sample[list(feature_columns)].to_numpy(dtype=float)
        y_train = train_sample[target_column].to_numpy(dtype=float)
        x_validation = validation_sample[list(feature_columns)].to_numpy(dtype=float)

        try:
            for candidate, fit in (
                ("ridge_log_vol", fit_log_volatility_regression),
                ("hist_gradient_boosting", fit_gradient_boosted_volatility),
            ):
                if candidate not in spec.candidate_models:
                    continue
                model = fit(x_train, y_train, random_seed=spec.random_seed)
                prediction = predict_volatility(model, x_validation)
                metrics[f"{candidate}_qlike"] = qlike_loss(actual, prediction)
                metrics[f"{candidate}_mae"] = mean_absolute_error(actual, prediction)
                if baseline_losses is not None:
                    # baseline MINUS candidate: positive means the candidate
                    # lost less than the frozen baseline on that row.
                    loss_rows.setdefault(candidate, []).append(
                        pd.DataFrame({
                            "as_of_session": sessions.to_numpy(),
                            "loss_difference": baseline_losses
                            - _pointwise_qlike(actual, prediction),
                        })
                    )
                if fold.fold_index == folds[-1].fold_index:
                    artifact_hashes[candidate] = save_model_artifact(
                        model, directory=output_directory,
                        filename=f"{spec.experiment_id}.{candidate}.joblib",
                    )
            metrics["fit_error"] = None
        except Exception as exc:  # a thin fold is recorded, never silently skipped
            metrics["fit_error"] = str(exc)
        fold_metrics.append(metrics)

    out_of_fold_losses = {
        candidate: pd.concat(frames, ignore_index=True)
        for candidate, frames in loss_rows.items()
    }
    aggregate: dict[str, Any] = {}
    for candidate in spec.candidate_models:
        result = dict(
            beats_baseline_in_multiple_folds(
                fold_metrics,
                candidate_key=f"{candidate}_qlike",
                baseline_key="ewma_qlike",
                lower_is_better=True,
                minimum_folds=spec.research_gate.minimum_folds_won,
            )
        )
        # Fold wins alone are a WEAK gate, and a pure-noise fixture proved it:
        # a candidate that merely learns the target's mean will beat a
        # miscalibrated baseline in every fold while having no skill at all.
        # Doc 14.1 lists beating the baseline in >1 fold as NECESSARY, not
        # sufficient -- so the preregistered alpha has to actually be tested,
        # not just recorded. Block-bootstrap the per-row QLIKE loss
        # DIFFERENCE (baseline minus candidate; positive means the candidate
        # loses less) across dates, using the same existing toolkit
        # ml/cross_sectional.py delegates to.
        differences = out_of_fold_losses.get(candidate)
        if differences is not None and not differences.empty:
            result["block_significance"] = {
                str(block_length): bootstrap_edge_significance_by_block(
                    differences["loss_difference"],
                    differences["as_of_session"],
                    block_length=block_length,
                    seed=spec.random_seed,
                )
                for block_length in spec.research_gate.block_lengths
            }
        else:
            result["block_significance"] = {}
        aggregate[candidate] = result
    return fold_metrics, artifact_hashes, aggregate


def _pointwise_qlike(actual: np.ndarray, predicted: np.ndarray) -> np.ndarray:
    """Per-row QLIKE loss, so a candidate and its baseline can be compared
    observation by observation rather than only as fold aggregates. Two
    aggregate numbers cannot support a bootstrap; per-row losses can."""
    ratio = np.square(actual) / np.square(predicted)
    return ratio - np.log(ratio) - 1.0


def _run_ranker_task(
    spec: ExperimentSpec,
    joined: pd.DataFrame,
    folds: Sequence[Any],
    *,
    feature_columns: Sequence[str],
    target_column: str,
    output_directory: Path,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, Any]]:
    fold_metrics: list[dict[str, Any]] = []
    artifact_hashes: dict[str, str] = {}
    out_of_fold: list[pd.DataFrame] = []

    for fold in folds:
        train = joined.iloc[list(fold.train_row_indices)]
        validation = joined.iloc[list(fold.validation_row_indices)].copy()
        columns = list(dict.fromkeys([*feature_columns, target_column]))
        train_sample = train[columns].apply(pd.to_numeric, errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        ).dropna()

        metrics: dict[str, Any] = {
            "fold_index": fold.fold_index,
            "train_start": fold.train_start,
            "train_end": fold.train_end,
            "validation_start": fold.validation_start,
            "validation_end": fold.validation_end,
            "train_row_count": len(train_sample),
            "validation_row_count": len(validation),
            "purged_row_count": fold.purged_row_count,
            "embargoed_row_count": fold.embargoed_row_count,
        }

        # --- frozen baseline FIRST: a no-skill constant score -------------
        validation["score_no_skill"] = 0.0
        baseline_fold = evaluate_ranker_fold(
            validation, score_column="score_no_skill", outcome_column=target_column
        )
        metrics["no_skill_mean_ic"] = baseline_fold["information_coefficient"]["mean_ic"]

        if train_sample.empty:
            metrics["fit_error"] = "no training rows survive finite filtering"
            fold_metrics.append(metrics)
            continue

        x_train = train_sample[list(feature_columns)].to_numpy(dtype=float)
        y_train = train_sample[target_column].to_numpy(dtype=float)
        validation_numeric = validation[list(feature_columns)].apply(
            pd.to_numeric, errors="coerce"
        ).replace([np.inf, -np.inf], np.nan)
        usable = validation_numeric.notna().all(axis=1)
        metrics["evaluated_validation_row_count"] = int(usable.sum())

        try:
            for candidate, fit in (
                ("elastic_net", fit_elastic_net_ranker),
                ("hist_gradient_boosting", fit_gradient_boosted_ranker),
            ):
                if candidate not in spec.candidate_models:
                    continue
                model = fit(x_train, y_train, random_seed=spec.random_seed)
                scores = pd.Series(np.nan, index=validation.index, dtype=float)
                if usable.any():
                    scores.loc[usable] = model.predict(
                        validation_numeric.loc[usable].to_numpy(dtype=float)
                    )
                column = f"score_{candidate}"
                validation[column] = scores
                fold_result = evaluate_ranker_fold(
                    validation, score_column=column, outcome_column=target_column
                )
                metrics[f"{candidate}_mean_ic"] = fold_result["information_coefficient"]["mean_ic"]
                metrics[f"{candidate}_positive_date_fraction"] = fold_result[
                    "information_coefficient"
                ]["positive_date_fraction"]
                metrics[f"{candidate}_quantile_spread"] = fold_result["quantile_spread"][
                    "mean_spread"
                ]
                if fold.fold_index == folds[-1].fold_index:
                    artifact_hashes[candidate] = save_model_artifact(
                        model, directory=output_directory,
                        filename=f"{spec.experiment_id}.{candidate}.joblib",
                    )
            metrics["fit_error"] = None
        except Exception as exc:
            metrics["fit_error"] = str(exc)

        # Plan 8.2 step 7: retain out-of-fold predictions keyed by their
        # independent date, so aggregate significance is computed across
        # untouched validation rows only -- never in-sample.
        keep = ["as_of_session", "ticker", target_column] + [
            c for c in validation.columns if c.startswith("score_")
        ]
        out_of_fold.append(validation[keep].assign(fold_index=fold.fold_index))
        fold_metrics.append(metrics)

    aggregate: dict[str, Any] = {}
    combined = pd.concat(out_of_fold, ignore_index=True) if out_of_fold else pd.DataFrame()
    for candidate in spec.candidate_models:
        column = f"score_{candidate}"
        if combined.empty or column not in combined.columns:
            continue
        ic = date_level_spearman_ic(
            combined.dropna(subset=[column]),
            score_column=column,
            outcome_column=target_column,
        )
        significance = {
            block_length: block_bootstrap_ic_significance(
                ic, block_length=block_length, seed=spec.random_seed
            )
            for block_length in spec.research_gate.block_lengths
        }
        aggregate[candidate] = {
            "out_of_fold_date_count": int(len(ic)),
            "mean_ic": round(float(ic.mean()), 6) if len(ic) else None,
            "block_significance": {str(k): v for k, v in significance.items()},
        }
    return fold_metrics, artifact_hashes, aggregate


def run_experiment(
    spec: ExperimentSpec,
    dataset_directory: Path,
    output_directory: Path,
    code_commit: str,
    *,
    dataset_id: str,
    feature_columns: Sequence[str],
    target_column: str = "label_value",
    trailing_baseline_column: str | None = None,
    ewma_baseline_column: str | None = None,
    generated_at: datetime | None = None,
) -> ExperimentRunRecord:
    """Run one reproducible experiment end to end (plan 8.2).

    Returns an ExperimentRunRecord. Writes the evaluation report, run
    manifest, and model artifacts into `output_directory` and NOTHING
    anywhere else -- no research-registry entry, no model registration, no
    proposal, no execution state (plan 8.2 step 12, and doc 17's outright
    prohibition on automatic promotion).
    """
    if spec.task not in SUPPORTED_TASKS:
        raise ExperimentError(
            f"unsupported task {spec.task!r}; supported: {SUPPORTED_TASKS}"
        )
    if not isinstance(code_commit, str) or not code_commit.strip():
        raise ExperimentError("code_commit is required for reproducibility")
    output_directory = Path(output_directory)
    # Experiment outputs are CONTENT-ADDRESSED, so wall-clock time is
    # deliberately excluded from them. Defaulting to datetime.now() made two
    # otherwise-identical runs produce different bytes, which broke plan
    # 8.6's definition of done ("a single command reproduces the same
    # fixture report and artifacts from the same spec/dataset/commit") and
    # turned an exact retry -- e.g. after a crash -- into a spurious
    # "refusing to overwrite" conflict. The unit test missed it by passing
    # an explicit fixed timestamp; only running the real CLI twice exposed
    # it.
    #
    # spec.created_at is used instead: it is a real, frozen, meaningful
    # timestamp (when this experiment was preregistered) rather than a
    # fabricated one, and it is already part of spec_hash. Actual execution
    # wall-clock is not research content -- the filesystem records it, and
    # a caller who needs it can pass generated_at explicitly.
    started_at = generated_at or _parse_spec_timestamp(spec)

    # 1. load and verify the dataset manifest and hashes
    features_df, labels_df, manifest = load_dataset(Path(dataset_directory), dataset_id)
    # 2. verify the spec matches the dataset
    _verify_spec_against_dataset(spec, manifest)

    joined = join_for_evaluation(features_df, labels_df, label_version=spec.label_version)
    _require_columns(joined, feature_columns, "joined dataset")
    _require_columns(joined, [target_column, "label_exit_session"], "joined dataset")

    # 3. purged grouped walk-forward folds
    n_splits, embargo = _fold_configuration(spec)
    folds = purged_grouped_walk_forward_splits(
        list(joined["as_of_session"]),
        list(joined["label_exit_session"]),
        n_splits=n_splits,
        embargo_sessions=embargo,
    )

    if spec.task == "volatility_forecast":
        if not trailing_baseline_column or not ewma_baseline_column:
            raise ExperimentError(
                "a volatility experiment requires trailing and EWMA baseline columns; "
                "doc 8.3 rejects a candidate that does not beat the EWMA baseline"
            )
        _require_columns(
            joined, [trailing_baseline_column, ewma_baseline_column], "joined dataset"
        )
        fold_metrics, artifact_hashes, aggregate = _run_volatility_task(
            spec, joined, folds,
            feature_columns=feature_columns, target_column=target_column,
            trailing_column=trailing_baseline_column, ewma_column=ewma_baseline_column,
            output_directory=output_directory,
        )
    else:
        fold_metrics, artifact_hashes, aggregate = _run_ranker_task(
            spec, joined, folds,
            feature_columns=feature_columns, target_column=target_column,
            output_directory=output_directory,
        )

    # 8. multiplicity-adjusted uncertainty
    total_looks = spec.total_research_looks()
    uncertainty = {
        "total_research_looks": total_looks,
        "bonferroni_alpha_threshold": bonferroni_threshold(total_looks),
        "preregistered_maximum_alpha": spec.research_gate.maximum_alpha,
        "aggregate": aggregate,
    }

    coverage_warnings: list[str] = []
    for metrics in fold_metrics:
        if metrics.get("fit_error"):
            coverage_warnings.append(
                f"fold_{metrics['fold_index']}_fit_error:{metrics['fit_error']}"
            )
        evaluated = metrics.get("evaluated_validation_row_count")
        total = metrics.get("validation_row_count") or 0
        if evaluated is not None and total and evaluated / total < spec.research_gate.minimum_coverage_fraction:
            coverage_warnings.append(
                f"fold_{metrics['fold_index']}_below_minimum_coverage"
            )

    verdict = _derive_verdict(spec, aggregate, coverage_warnings, manifest)

    report = EvaluationReport(
        research_question=spec.primary_outcome,
        preregistered_primary_outcome=spec.primary_outcome,
        candidate_models=spec.candidate_models,
        baselines=spec.frozen_baselines,
        simultaneous_research_looks=total_looks,
        dataset_hash=manifest.dataset_hash,
        feature_set_version=spec.feature_set_version,
        point_in_time_data=manifest.point_in_time_data,
        survivorship_bias_note=(
            f"universe={spec.universe_definition}; "
            f"point_in_time_data={manifest.point_in_time_data}"
        ),
        split_summary=tuple(fold.to_dict() for fold in folds),
        entry_timing=manifest.entry_timing,
        cost_tax_capital_assumptions=dict(spec.cost_tax_liquidity_assumptions),
        fold_metrics=tuple(fold_metrics),
        aggregate_metrics=aggregate,
        dependence_aware_uncertainty=uncertainty,
        failure_analysis={"failure_slices": list(spec.research_gate.failure_slices)},
        calibration=(),
        coverage_warnings=tuple(coverage_warnings),
        limitations=_limitations(spec, manifest),
        verdict=verdict,
        generated_at=started_at.isoformat(),
    )

    report_payload = report.to_dict()
    report_bytes = canonical_json(report_payload).encode("utf-8")
    _atomic_write(output_directory, f"{spec.experiment_id}.report.json", report_bytes)
    spec_bytes = canonical_json(spec.to_dict()).encode("utf-8")
    _atomic_write(output_directory, f"{spec.experiment_id}.spec.json", spec_bytes)

    # Same determinism rule as started_at: the run manifest is content-
    # addressed, so an exact retry reproduces it byte for byte.
    completed_at = started_at
    record = ExperimentRunRecord(
        identity=spec.identity(),
        dataset_id=dataset_id,
        dataset_hash=manifest.dataset_hash,
        code_commit=code_commit,
        started_at=started_at.isoformat(),
        completed_at=completed_at.isoformat(),
        report_hash=hash_bytes(report_bytes),
        artifact_hashes=artifact_hashes,
        total_research_looks=total_looks,
        verdict=verdict,
        promotion_blockers=tuple(report.promotion_blockers()),
    )
    # 11. run manifest containing every output hash
    _atomic_write(
        output_directory,
        f"{spec.experiment_id}.run.json",
        canonical_json(record.to_dict()).encode("utf-8"),
    )
    return record


def _limitations(spec: ExperimentSpec, manifest: Any) -> tuple[str, ...]:
    limitations = [
        "Tests verify software behavior, not market edge (strategy doc 19.6).",
        "No research-registry entry is written by this runner.",
    ]
    if not manifest.point_in_time_data:
        limitations.append(
            "Dataset is not point-in-time; every result here is exploratory and "
            "promotion-blocked."
        )
    if spec.mode == "discovery":
        limitations.append(
            "Discovery run: a positive result requires a separate confirmation "
            "experiment with a new immutable experiment_id."
        )
    return tuple(limitations)


def _derive_verdict(
    spec: ExperimentSpec,
    aggregate: Mapping[str, Any],
    coverage_warnings: Sequence[str],
    manifest: Any,
) -> str:
    """Derive the verdict from the PREREGISTERED gate, never from inspection.

    A discovery run can never return "promising_unconfirmed" no matter how
    good it looks: plan 8.4 requires a separate confirmation experiment, and
    letting discovery self-certify would collapse the two-stage discipline
    the whole plan is built on.
    """
    if coverage_warnings:
        return "rejected"
    alpha = min(
        spec.research_gate.maximum_alpha,
        bonferroni_threshold(spec.total_research_looks()),
    )
    passed: list[str] = []
    for name, result in aggregate.items():
        if not isinstance(result, Mapping) or not result.get("passes"):
            continue
        # Fold wins are necessary but NOT sufficient (doc 14.1). The
        # preregistered alpha, tightened by the multiplicity correction, has
        # to actually be met at EVERY declared block length -- a result that
        # only survives one convenient block length is exactly the
        # "directionally stable under reasonable block lengths" condition
        # doc 14.1 asks for, failing.
        significance = result.get("block_significance") or {}
        if not significance:
            continue
        p_values = [
            entry.get("p_value")
            for entry in significance.values()
            if isinstance(entry, Mapping)
        ]
        if not p_values or any(p is None for p in p_values):
            continue
        if all(float(p) < alpha for p in p_values):
            passed.append(name)
    if spec.mode == "discovery":
        return "confirmation_run_requested" if passed else "rejected"
    if not passed:
        return "rejected"
    if not manifest.point_in_time_data:
        # A confirmation run on non-point-in-time data cannot be called
        # promising -- doc 3.4 makes that a promotion blocker.
        return "exploratory"
    return "promising_unconfirmed"
