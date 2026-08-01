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
import importlib.metadata
import json
import re
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from backtest.engine import (
    bonferroni_threshold,
    bootstrap_edge_significance_by_block,
)
from assistant.schemas import EvidenceStatus
from ml.artifacts import (
    load_model_artifact,
    load_model_manifest,
    save_model_artifact,
    save_model_manifest,
)
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
    mean_absolute_error,
    qlike_loss,
)
from ml.experiment_contracts import (
    ExperimentRunRecord,
    ExperimentSpec,
)
from ml.hashing import canonical_json, hash_bytes
from ml.volatility_evaluation import (
    MIN_RESIDUALS_FOR_INTERVAL,
    CalibrationStatus,
    aggregate_interval_coverage,
    evaluate_by_slice,
    evaluate_ceiling_calibration,
    evaluate_warning_behavior,
    expanding_out_of_fold_intervals,
)
from ml.splits import purged_grouped_walk_forward_splits
from ml.transforms import apply_training_standardizer, fit_training_standardizer
from ml.volatility import (
    fit_gradient_boosted_volatility,
    fit_log_volatility_regression,
    predict_volatility,
)

SUPPORTED_TASKS = ("volatility_forecast", "cross_sectional_excess_return_ranking")
_VOLATILITY_CANDIDATES = frozenset({"ridge_log_vol", "hist_gradient_boosting"})
_VOLATILITY_BASELINES = frozenset({"trailing_realized", "ewma"})
_RANKER_CANDIDATES = frozenset({"elastic_net", "hist_gradient_boosting"})
_RANKER_BASELINES = frozenset({"no_skill"})
_SAFE_EXPERIMENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_COMMIT_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


class ExperimentError(ValueError):
    """An experiment cannot be run reproducibly as specified."""


@dataclasses.dataclass(frozen=True)
class _FittedModel:
    estimator: Any
    standardizer: Any
    algorithm: str
    hyperparameters: Mapping[str, Any]
    training_start: str
    training_end: str


def _require_safe_output_name(filename: str) -> None:
    if (
        not isinstance(filename, str)
        or not filename
        or filename in {".", ".."}
        or Path(filename).name != filename
        or "/" in filename
        or "\\" in filename
        or "\x00" in filename
    ):
        raise ExperimentError("experiment output filename must be one plain file name")


def _atomic_write(directory: Path, filename: str, data: bytes) -> Path:
    """Immutable write: an existing byte-identical file is a no-op (so an
    exact rerun is idempotent), a differing one is refused (so a conflicting
    rerun cannot silently overwrite an earlier run's evidence)."""
    import os
    import tempfile

    _require_safe_output_name(filename)
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
    if spec.benchmark != getattr(manifest, "benchmark", None):
        mismatches.append(
            f"benchmark: spec={spec.benchmark!r} "
            f"dataset={getattr(manifest, 'benchmark', None)!r}"
        )
    if mismatches:
        raise ExperimentError(
            "spec does not match the dataset it was run against: " + "; ".join(mismatches)
        )


def _validate_task_configuration(
    spec: ExperimentSpec,
    *,
    feature_columns: Sequence[str],
    target_column: str,
    trailing_baseline_column: str | None,
    ewma_baseline_column: str | None,
) -> tuple[str, ...]:
    """Bind every behavior-changing runner argument to the hashed spec."""
    features = tuple(feature_columns)
    if not spec.ordered_feature_names:
        raise ExperimentError(
            "the experiment spec must freeze ordered_feature_names before it can run"
        )
    if features != spec.ordered_feature_names:
        raise ExperimentError(
            "feature_columns does not match spec.ordered_feature_names exactly "
            f"(including order): runner={features!r} spec={spec.ordered_feature_names!r}"
        )
    if target_column != spec.target_column:
        raise ExperimentError(
            f"target_column {target_column!r} does not match frozen spec target "
            f"{spec.target_column!r}"
        )

    candidates = set(spec.candidate_models)
    baselines = set(spec.frozen_baselines)
    if spec.task == "volatility_forecast":
        unsupported = candidates - _VOLATILITY_CANDIDATES
        if unsupported:
            raise ExperimentError(f"unsupported volatility candidates: {sorted(unsupported)}")
        if baselines != _VOLATILITY_BASELINES:
            raise ExperimentError(
                "volatility frozen_baselines must be exactly trailing_realized and ewma"
            )
        if not trailing_baseline_column or not ewma_baseline_column:
            raise ExperimentError(
                "a volatility experiment requires trailing and EWMA baseline columns"
            )
        expected = {
            "trailing_realized": trailing_baseline_column,
            "ewma": ewma_baseline_column,
        }
        if dict(spec.baseline_columns) != expected:
            raise ExperimentError(
                "runner baseline columns do not match spec.baseline_columns: "
                f"runner={expected!r} spec={dict(spec.baseline_columns)!r}"
            )
    else:
        unsupported = candidates - _RANKER_CANDIDATES
        if unsupported:
            raise ExperimentError(f"unsupported ranker candidates: {sorted(unsupported)}")
        if baselines != _RANKER_BASELINES:
            raise ExperimentError("ranker frozen_baselines must be exactly no_skill")
        if spec.baseline_columns:
            raise ExperimentError("ranker baseline_columns must be empty for no_skill")
        if trailing_baseline_column is not None or ewma_baseline_column is not None:
            raise ExperimentError("ranker runs do not accept volatility baseline columns")
    return features


def _read_json_object(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        data = path.read_bytes()
        payload = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExperimentError(f"could not read {label} at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ExperimentError(f"{label} at {path} must contain one JSON object")
    return data, payload


def _confirmation_behavior(spec: ExperimentSpec) -> dict[str, Any]:
    payload = spec.to_dict()
    for key in ("experiment_id", "mode", "created_at", "confirmation"):
        payload.pop(key, None)
    return payload


def _verify_confirmation_parent(spec: ExperimentSpec, output_directory: Path) -> None:
    if spec.mode != "confirmation":
        return
    parent = spec.confirmation
    if parent is None:  # the contract already rejects this; keep the runner fail-closed
        raise ExperimentError("confirmation spec is missing its parent")
    prefix = parent.parent_experiment_id
    spec_bytes, spec_payload = _read_json_object(
        output_directory / f"{prefix}.spec.json", "parent discovery spec"
    )
    del spec_bytes  # identity is the contract's canonical spec hash, not file formatting
    try:
        parent_spec = ExperimentSpec.from_dict(spec_payload)
    except ValueError as exc:
        raise ExperimentError(f"parent discovery spec failed validation: {exc}") from exc
    if parent_spec.experiment_id != prefix or parent_spec.mode != "discovery":
        raise ExperimentError("confirmation parent must resolve to the named discovery spec")
    if parent_spec.spec_hash != parent.parent_spec_hash:
        raise ExperimentError(
            "parent discovery spec hash does not match confirmation.parent_spec_hash"
        )
    if _confirmation_behavior(parent_spec) != _confirmation_behavior(spec):
        raise ExperimentError(
            "confirmation changes behavior frozen by its parent discovery spec"
        )

    report_bytes, report_payload = _read_json_object(
        output_directory / f"{prefix}.report.json", "parent discovery report"
    )
    if hash_bytes(report_bytes) != parent.parent_report_hash:
        raise ExperimentError(
            "parent discovery report hash does not match confirmation.parent_report_hash"
        )
    _, run_payload = _read_json_object(
        output_directory / f"{prefix}.run.json", "parent discovery run"
    )
    try:
        parent_run = ExperimentRunRecord.from_dict(run_payload)
    except ValueError as exc:
        raise ExperimentError(f"parent discovery run failed validation: {exc}") from exc
    if (
        parent_run.identity.spec_hash != parent_spec.spec_hash
        or parent_run.report_hash != parent.parent_report_hash
        or parent_run.verdict != "confirmation_run_requested"
        or report_payload.get("verdict") != "confirmation_run_requested"
    ):
        raise ExperimentError(
            "parent discovery did not produce a verified confirmation request"
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
    if spec.research_gate.minimum_folds_won > n_splits:
        raise ExperimentError(
            "research_gate.minimum_folds_won cannot exceed split_configuration.n_splits"
        )
    if any(length < spec.horizon_sessions for length in spec.research_gate.block_lengths):
        raise ExperimentError(
            "every research_gate.block_length must be at least horizon_sessions "
            "to cover overlapping outcome windows"
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
) -> tuple[list[dict[str, Any]], dict[str, _FittedModel], dict[str, Any]]:
    """Fit frozen baselines first, then candidates, on identical rows."""
    fold_metrics: list[dict[str, Any]] = []
    fitted_models: dict[str, _FittedModel] = {}
    # Out-of-fold per-row QLIKE losses, retained by their independent date so
    # aggregate significance is computed across untouched validation rows
    # only (plan 8.2 step 7).
    loss_rows: dict[str, list[pd.DataFrame]] = {}
    fold_predictions: dict[str, list[dict[str, Any]]] = {}

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

        transformed = apply_training_standardizer(joined, standardizer)
        standardized_columns = [f"{name}__standardized" for name in feature_columns]
        x_train = transformed.loc[train_sample.index, standardized_columns].to_numpy(
            dtype=float
        )
        y_train = train_sample[target_column].to_numpy(dtype=float)
        x_validation = transformed.loc[
            validation_sample.index, standardized_columns
        ].to_numpy(dtype=float)

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
                # Retain raw per-fold prediction/actual pairs so ML-LR-3's
                # interval, calibration, warning, and slice reports can be
                # computed from untouched validation rows after every fold has
                # been scored (plan 9.4).
                fold_predictions.setdefault(candidate, []).append(
                    {
                        "fold_index": fold.fold_index,
                        "actual": actual,
                        "predicted": prediction,
                        "sessions": sessions.to_numpy(),
                        "tickers": (
                            joined.loc[validation_sample.index, "ticker"].to_numpy()
                            if "ticker" in joined.columns
                            else np.array([""] * len(actual))
                        ),
                        "trailing": validation_sample[trailing_column].to_numpy(dtype=float),
                        "ewma": validation_sample[ewma_column].to_numpy(dtype=float),
                    }
                )
                if fold.fold_index == folds[-1].fold_index:
                    fitted_models[candidate] = _FittedModel(
                        estimator=model,
                        standardizer=standardizer,
                        algorithm=type(model).__name__,
                        hyperparameters=(
                            {"alpha": 1.0}
                            if candidate == "ridge_log_vol"
                            else {"max_iter": 200, "early_stopping": False}
                        ),
                        training_start=standardizer.training_start,
                        training_end=standardizer.training_end,
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
        result.update(
            _volatility_evaluation_reports(spec, fold_predictions.get(candidate, []))
        )
        aggregate[candidate] = result
    return fold_metrics, fitted_models, aggregate


def _volatility_evaluation_reports(
    spec: ExperimentSpec, predictions: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Plan 9.4's completion reports, computed from untouched validation rows.

    Everything here is REPORTING. The preregistered gate in _derive_verdict()
    decides what the numbers mean; this function never returns a pass/fail.
    """
    if not predictions:
        return {"interval_report": [], "interval_coverage": {}, "slice_report": {}}

    intervals = expanding_out_of_fold_intervals(predictions)
    reports: dict[str, Any] = {
        "interval_report": intervals,
        "interval_coverage": aggregate_interval_coverage(intervals),
    }

    frame = pd.DataFrame(
        {
            "as_of_session": np.concatenate([p["sessions"] for p in predictions]),
            "ticker": np.concatenate([p["tickers"] for p in predictions]),
            "actual": np.concatenate([p["actual"] for p in predictions]),
            "model_predicted": np.concatenate([p["predicted"] for p in predictions]),
            "trailing_predicted": np.concatenate([p["trailing"] for p in predictions]),
            "ewma_predicted": np.concatenate([p["ewma"] for p in predictions]),
        }
    )
    frame["year"] = frame["as_of_session"].astype(str).str.slice(0, 4)
    # Volatility regime is derived from the ACTUAL realized level, which is a
    # description of the period rather than a model input -- it slices results,
    # it never feeds a prediction.
    median_actual = float(frame["actual"].median())
    frame["volatility_regime"] = np.where(
        frame["actual"] > median_actual, "high", "low"
    )
    reports["slice_report"] = evaluate_by_slice(frame)

    ceiling = spec.research_gate.mandate_ceiling_daily_pct
    if ceiling is None:
        # Doc 9.4 requires a PREREGISTERED ceiling. Without one there is
        # nothing honest to calibrate against, so this reports its absence
        # rather than inventing a threshold from the observed distribution --
        # which would be choosing the bar after seeing the results.
        reports["ceiling_calibration"] = {
            "calibration_status": CalibrationStatus.NOT_MEASURED,
            "insufficiency_reason": (
                "no mandate_ceiling_daily_pct was preregistered in the research gate"
            ),
        }
        reports["warning_behavior"] = {}
        return reports

    reports["warning_behavior"] = evaluate_warning_behavior(
        frame, ceiling_pct=ceiling
    )
    # Threshold probabilities come from the SAME expanding out-of-fold
    # residual history the intervals use, so a probability for fold k is
    # informed only by folds < k.
    probabilities: list[float] = []
    actuals: list[float] = []
    prior: list[float] = []
    for prediction in predictions:
        actual = np.asarray(prediction["actual"], dtype=float)
        predicted = np.asarray(prediction["predicted"], dtype=float)
        usable = np.isfinite(actual) & np.isfinite(predicted) & (actual > 0) & (predicted > 0)
        if len(prior) >= MIN_RESIDUALS_FOR_INTERVAL and usable.any():
            residuals = np.asarray(prior, dtype=float)
            for point in predicted[usable]:
                implied = point * np.exp(residuals)
                probabilities.append(float(np.mean(implied > ceiling)))
            actuals.extend(actual[usable].tolist())
        prior.extend(np.log(actual[usable] / predicted[usable]).tolist())

    reports["ceiling_calibration"] = evaluate_ceiling_calibration(
        actuals, probabilities,
        ceiling_pct=ceiling,
        n_bins=spec.research_gate.required_calibration_bins,
        maximum_brier=spec.research_gate.maximum_brier,
    )
    return reports


def _pointwise_qlike(actual: np.ndarray, predicted: np.ndarray) -> np.ndarray:
    """Per-row QLIKE loss, so a candidate and its baseline can be compared
    observation by observation rather than only as fold aggregates. Two
    aggregate numbers cannot support a bootstrap; per-row losses can."""
    ratio = np.square(actual) / np.square(predicted)
    return ratio - np.log(ratio) - 1.0


def _dependency_versions() -> dict[str, str]:
    return {
        package: importlib.metadata.version(package)
        for package in ("numpy", "pandas", "scikit-learn", "joblib")
    }


def _evidence_status(verdict: str) -> EvidenceStatus:
    if verdict == "rejected":
        return EvidenceStatus.REJECTED
    if verdict == "promising_unconfirmed":
        return EvidenceStatus.PROMISING_UNCONFIRMED
    return EvidenceStatus.EXPLORATORY


def _save_and_verify_models(
    *,
    spec: ExperimentSpec,
    fitted_models: Mapping[str, _FittedModel],
    output_directory: Path,
    dataset_id: str,
    dataset_hash: str,
    report_hash: str,
    created_at: str,
    folds: Sequence[Any],
    verdict: str,
) -> dict[str, str]:
    """Persist typed model bundles and prove their bytes reload under manifests."""
    hashes: dict[str, str] = {}
    validation_windows = tuple(
        {"start": fold.validation_start, "end": fold.validation_end}
        for fold in folds
    )
    for candidate, fitted in fitted_models.items():
        artifact_filename = f"{spec.experiment_id}.{candidate}.joblib"
        manifest_filename = f"{spec.experiment_id}.{candidate}.manifest.json"
        bundle = {
            "estimator": fitted.estimator,
            "standardizer": {
                "feature_names": tuple(fitted.standardizer.feature_names),
                "means": dict(fitted.standardizer.means),
                "scales": dict(fitted.standardizer.scales),
                "training_row_count": fitted.standardizer.training_row_count,
                "training_start": fitted.standardizer.training_start,
                "training_end": fitted.standardizer.training_end,
            },
            "ordered_feature_names": spec.ordered_feature_names,
        }
        artifact_hash = save_model_artifact(
            bundle,
            directory=output_directory,
            filename=artifact_filename,
        )
        manifest = ModelManifest(
            model_id=f"{spec.experiment_id}.{candidate}",
            model_version=spec.spec_hash,
            task=spec.task,
            created_at=created_at,
            dataset_id=dataset_id,
            dataset_hash=dataset_hash,
            feature_set_version=spec.feature_set_version,
            ordered_feature_names=spec.ordered_feature_names,
            label_version=spec.label_version,
            algorithm=fitted.algorithm,
            hyperparameters={
                **dict(fitted.hyperparameters),
                "training_only_standardizer": True,
            },
            random_seed=spec.random_seed,
            training_window={
                "start": fitted.training_start,
                "end": fitted.training_end,
            },
            validation_windows=validation_windows,
            dependency_versions=_dependency_versions(),
            artifact_hash=artifact_hash,
            evaluation_report_hash=report_hash,
            evidence_status=_evidence_status(verdict),
        )
        manifest_hash = save_model_manifest(
            manifest,
            directory=output_directory,
            filename=manifest_filename,
        )
        reloaded_manifest = load_model_manifest(
            directory=output_directory,
            filename=manifest_filename,
            model_id=manifest.model_id,
            model_version=manifest.model_version,
            expected_manifest_hash=manifest_hash,
        )
        with warnings.catch_warnings():
            # joblib 1.5.3 mutates ndarray.shape while reconstructing arrays;
            # NumPy 2.5 deprecates that internal implementation detail. It is
            # unrelated to artifact integrity and otherwise emits hundreds of
            # warnings per tree-based model verification.
            warnings.filterwarnings(
                "ignore",
                message="Setting the shape on a NumPy array has been deprecated.*",
                category=DeprecationWarning,
            )
            reloaded = load_model_artifact(
                reloaded_manifest,
                directory=output_directory,
                filename=artifact_filename,
            )
        if (
            not isinstance(reloaded, dict)
            or tuple(reloaded.get("ordered_feature_names", ()))
            != spec.ordered_feature_names
            or "estimator" not in reloaded
            or "standardizer" not in reloaded
        ):
            raise ExperimentError(
                f"reloaded model bundle for {candidate!r} failed structural verification"
            )
        hashes[f"{candidate}.artifact"] = artifact_hash
        hashes[f"{candidate}.manifest"] = manifest_hash
    return hashes


def _run_ranker_task(
    spec: ExperimentSpec,
    joined: pd.DataFrame,
    folds: Sequence[Any],
    *,
    feature_columns: Sequence[str],
    target_column: str,
) -> tuple[list[dict[str, Any]], dict[str, _FittedModel], dict[str, Any]]:
    fold_metrics: list[dict[str, Any]] = []
    fitted_models: dict[str, _FittedModel] = {}
    out_of_fold: list[pd.DataFrame] = []

    for fold in folds:
        train = joined.iloc[list(fold.train_row_indices)]
        validation = joined.iloc[list(fold.validation_row_indices)].copy()
        columns = list(dict.fromkeys([*feature_columns, target_column]))
        train_sample = train[columns].apply(pd.to_numeric, errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        ).dropna()
        validation_sample = validation[columns].apply(
            pd.to_numeric, errors="coerce"
        ).replace([np.inf, -np.inf], np.nan).dropna()
        validation_eval = validation.loc[validation_sample.index].copy()
        validation_eval[target_column] = validation_sample[target_column]

        metrics: dict[str, Any] = {
            "fold_index": fold.fold_index,
            "train_start": fold.train_start,
            "train_end": fold.train_end,
            "validation_start": fold.validation_start,
            "validation_end": fold.validation_end,
            "train_row_count": len(train_sample),
            "validation_row_count": len(validation),
            "evaluated_validation_row_count": len(validation_eval),
            "purged_row_count": fold.purged_row_count,
            "embargoed_row_count": fold.embargoed_row_count,
        }

        # --- frozen baseline FIRST: a no-skill constant score -------------
        validation_eval["score_no_skill"] = 0.0
        baseline_fold = evaluate_ranker_fold(
            validation_eval, score_column="score_no_skill", outcome_column=target_column
        )
        metrics["no_skill_mean_ic"] = baseline_fold["information_coefficient"]["mean_ic"]

        if train_sample.empty:
            metrics["fit_error"] = "no training rows survive finite filtering"
            fold_metrics.append(metrics)
            continue

        if validation_eval.empty:
            metrics["fit_error"] = "no validation rows survive finite filtering"
            fold_metrics.append(metrics)
            continue

        standardizer = fit_training_standardizer(
            joined,
            list(feature_columns),
            train_row_indices=list(train_sample.index),
        )
        transformed = apply_training_standardizer(joined, standardizer)
        standardized_columns = [f"{name}__standardized" for name in feature_columns]
        metrics["standardizer_training_rows"] = standardizer.training_row_count
        metrics["standardizer_training_window"] = [
            standardizer.training_start,
            standardizer.training_end,
        ]
        x_train = transformed.loc[train_sample.index, standardized_columns].to_numpy(
            dtype=float
        )
        y_train = train_sample[target_column].to_numpy(dtype=float)
        x_validation = transformed.loc[
            validation_eval.index, standardized_columns
        ].to_numpy(dtype=float)

        try:
            for candidate, fit in (
                ("elastic_net", fit_elastic_net_ranker),
                ("hist_gradient_boosting", fit_gradient_boosted_ranker),
            ):
                if candidate not in spec.candidate_models:
                    continue
                model = fit(x_train, y_train, random_seed=spec.random_seed)
                scores = pd.Series(
                    model.predict(x_validation), index=validation_eval.index, dtype=float
                )
                column = f"score_{candidate}"
                validation_eval[column] = scores
                fold_result = evaluate_ranker_fold(
                    validation_eval, score_column=column, outcome_column=target_column
                )
                metrics[f"{candidate}_mean_ic"] = fold_result["information_coefficient"]["mean_ic"]
                metrics[f"{candidate}_positive_date_fraction"] = fold_result[
                    "information_coefficient"
                ]["positive_date_fraction"]
                metrics[f"{candidate}_quantile_spread"] = fold_result["quantile_spread"][
                    "mean_spread"
                ]
                if fold.fold_index == folds[-1].fold_index:
                    fitted_models[candidate] = _FittedModel(
                        estimator=model,
                        standardizer=standardizer,
                        algorithm=type(model).__name__,
                        hyperparameters=(
                            {"alpha": 0.01, "l1_ratio": 0.5, "max_iter": 5000}
                            if candidate == "elastic_net"
                            else {"max_iter": 200, "early_stopping": False}
                        ),
                        training_start=standardizer.training_start,
                        training_end=standardizer.training_end,
                    )
            metrics["fit_error"] = None
        except Exception as exc:
            metrics["fit_error"] = str(exc)

        # Plan 8.2 step 7: retain out-of-fold predictions keyed by their
        # independent date, so aggregate significance is computed across
        # untouched validation rows only -- never in-sample.
        keep = ["as_of_session", "ticker", target_column] + [
            c for c in validation_eval.columns if c.startswith("score_")
        ]
        out_of_fold.append(validation_eval[keep].assign(fold_index=fold.fold_index))
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
        per_fold = []
        folds_won = 0
        comparable_folds = 0
        for metrics in fold_metrics:
            value = metrics.get(f"{candidate}_mean_ic")
            comparable = value is not None and np.isfinite(float(value))
            won = bool(comparable and float(value) > 0.0)
            comparable_folds += int(comparable)
            folds_won += int(won)
            per_fold.append(
                {
                    "fold_index": metrics["fold_index"],
                    "comparable": bool(comparable),
                    "won": won,
                }
            )
        aggregate[candidate] = {
            "out_of_fold_date_count": int(len(ic)),
            "mean_ic": round(float(ic.mean()), 6) if len(ic) else None,
            "block_significance": {str(k): v for k, v in significance.items()},
            "comparable_folds": comparable_folds,
            "folds_won": folds_won,
            "minimum_folds_required": spec.research_gate.minimum_folds_won,
            "passes": (
                comparable_folds >= spec.research_gate.minimum_folds_won
                and folds_won >= spec.research_gate.minimum_folds_won
            ),
            "per_fold": per_fold,
        }
    return fold_metrics, fitted_models, aggregate


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
    if not isinstance(code_commit, str) or _COMMIT_PATTERN.fullmatch(code_commit) is None:
        raise ExperimentError("code_commit must be a lowercase 40- or 64-character git hash")
    if _SAFE_EXPERIMENT_ID.fullmatch(spec.experiment_id) is None:
        raise ExperimentError(
            "experiment_id must be 1-128 path-safe letters, numbers, periods, "
            "underscores, or hyphens"
        )
    output_directory = Path(output_directory)
    _verify_confirmation_parent(spec, output_directory)
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
    started_at = _parse_spec_timestamp(spec)
    if generated_at is not None:
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            raise ExperimentError("generated_at must be timezone-aware")
        if generated_at != started_at:
            raise ExperimentError(
                "generated_at is frozen by spec.created_at and cannot vary independently"
            )

    # 1. load and verify the dataset manifest and hashes
    features_df, labels_df, manifest = load_dataset(Path(dataset_directory), dataset_id)
    # 2. verify the spec matches the dataset
    _verify_spec_against_dataset(spec, manifest)
    feature_columns = _validate_task_configuration(
        spec,
        feature_columns=feature_columns,
        target_column=target_column,
        trailing_baseline_column=trailing_baseline_column,
        ewma_baseline_column=ewma_baseline_column,
    )

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
        fold_metrics, fitted_models, aggregate = _run_volatility_task(
            spec, joined, folds,
            feature_columns=feature_columns, target_column=target_column,
            trailing_column=trailing_baseline_column, ewma_column=ewma_baseline_column,
        )
    else:
        fold_metrics, fitted_models, aggregate = _run_ranker_task(
            spec, joined, folds,
            feature_columns=feature_columns, target_column=target_column,
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
    report_hash = hash_bytes(report_bytes)
    _atomic_write(output_directory, f"{spec.experiment_id}.report.json", report_bytes)
    spec_bytes = canonical_json(spec.to_dict()).encode("utf-8")
    _atomic_write(output_directory, f"{spec.experiment_id}.spec.json", spec_bytes)

    # 10. Artifacts carry their training-only transform and a ModelManifest,
    # then are hash-verified and deserialized through the sanctioned loader.
    artifact_hashes = _save_and_verify_models(
        spec=spec,
        fitted_models=fitted_models,
        output_directory=output_directory,
        dataset_id=dataset_id,
        dataset_hash=manifest.dataset_hash,
        report_hash=report_hash,
        created_at=started_at.isoformat(),
        folds=folds,
        verdict=verdict,
    )

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
        report_hash=report_hash,
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
