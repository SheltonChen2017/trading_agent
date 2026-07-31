"""Evaluation metrics and the immutable evaluation-report contract
(strategy doc sections 8.3, 9.4, 11.4, 14).

Every metric here refuses rather than guesses: too few observations, a
non-finite input, or a non-positive volatility returns None (or raises)
instead of a number that would look like evidence. Doc 19.6: "Do not claim
a model works based on tests; tests verify software behavior, not market
edge."

Dependence-aware significance is NOT reimplemented here. This project
already owns a carefully-built toolkit for that
(backtest/engine.py's bootstrap_edge_significance_by_block,
out_of_sample_significance_by_block, bonferroni_threshold), and the
project's own standing rule is to never trust pooled or row-level
significance. ml/cross_sectional.py calls that existing toolkit directly.
"""
from __future__ import annotations

import dataclasses
import math
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from ml.hashing import hash_payload


class EvaluationError(ValueError):
    """Inputs cannot support a trustworthy metric."""


def _finite_pairs(
    actual: Sequence[float], predicted: Sequence[float]
) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(actual, dtype=float)
    p = np.asarray(predicted, dtype=float)
    if a.shape != p.shape:
        raise EvaluationError("actual and predicted must have the same shape")
    mask = np.isfinite(a) & np.isfinite(p)
    return a[mask], p[mask]


def qlike_loss(actual_volatility: Sequence[float], predicted_volatility: Sequence[float]) -> float | None:
    """QLIKE loss (doc 8.3's primary volatility metric).

    QLIKE = mean( actual_var/pred_var - log(actual_var/pred_var) - 1 ).
    Preferred over MSE for volatility because it is robust to the fact that
    a volatility "actual" is itself a noisy estimate, and it penalizes
    UNDER-prediction much harder than over-prediction -- the asymmetry that
    matters for a risk forecast, where being surprised by more volatility
    than expected is the expensive error.

    Lower is better. Returns None if no usable pair survives.
    """
    a, p = _finite_pairs(actual_volatility, predicted_volatility)
    mask = (a > 0) & (p > 0)
    a, p = a[mask], p[mask]
    if a.size == 0:
        return None
    ratio = np.square(a) / np.square(p)
    loss = float(np.mean(ratio - np.log(ratio) - 1.0))
    return loss if math.isfinite(loss) else None


def mean_absolute_error(actual: Sequence[float], predicted: Sequence[float]) -> float | None:
    a, p = _finite_pairs(actual, predicted)
    if a.size == 0:
        return None
    value = float(np.mean(np.abs(a - p)))
    return value if math.isfinite(value) else None


def interval_coverage(
    actual: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float],
) -> float | None:
    """Fraction of actuals falling inside their predicted interval.

    A 90% interval that covers 55% of outcomes is not "roughly right" -- it
    is a miscalibrated interval that will understate risk exactly when it
    matters, which is why doc 8.3 lists coverage as a primary metric.
    """
    a = np.asarray(actual, dtype=float)
    lo = np.asarray(lower, dtype=float)
    hi = np.asarray(upper, dtype=float)
    if not (a.shape == lo.shape == hi.shape):
        raise EvaluationError("actual, lower, and upper must have the same shape")
    mask = np.isfinite(a) & np.isfinite(lo) & np.isfinite(hi)
    a, lo, hi = a[mask], lo[mask], hi[mask]
    if a.size == 0:
        return None
    if np.any(hi < lo):
        raise EvaluationError("upper bound is below lower bound")
    return float(np.mean((a >= lo) & (a <= hi)))


def brier_score(actual_binary: Sequence[float], predicted_probability: Sequence[float]) -> float | None:
    """Mean squared error of a probability forecast (doc 9.4). Lower better."""
    a, p = _finite_pairs(actual_binary, predicted_probability)
    if a.size == 0:
        return None
    if np.any((a != 0) & (a != 1)):
        raise EvaluationError("actual_binary must contain only 0 or 1")
    if np.any((p < 0) | (p > 1)):
        raise EvaluationError("predicted_probability must be within [0, 1]")
    return float(np.mean(np.square(p - a)))


def log_loss(
    actual_binary: Sequence[float],
    predicted_probability: Sequence[float],
    *,
    epsilon: float = 1e-15,
) -> float | None:
    """Binary cross-entropy (doc 9.4). Clipped so a confident wrong answer
    yields a large finite penalty rather than infinity."""
    a, p = _finite_pairs(actual_binary, predicted_probability)
    if a.size == 0:
        return None
    if np.any((a != 0) & (a != 1)):
        raise EvaluationError("actual_binary must contain only 0 or 1")
    if np.any((p < 0) | (p > 1)):
        raise EvaluationError("predicted_probability must be within [0, 1]")
    clipped = np.clip(p, epsilon, 1 - epsilon)
    return float(-np.mean(a * np.log(clipped) + (1 - a) * np.log(1 - clipped)))


def calibration_curve(
    actual_binary: Sequence[float],
    predicted_probability: Sequence[float],
    *,
    n_bins: int = 10,
) -> list[dict[str, Any]]:
    """Observed frequency vs predicted probability, by bin (doc 9.4).

    Doc 16: "Never display a raw model probability as 'confidence' unless
    calibration has been measured and the exact meaning is stated." This is
    that measurement. Empty bins are reported with count 0 rather than
    dropped, so a model that only ever predicts one narrow band is visibly
    doing so.
    """
    if n_bins < 2:
        raise EvaluationError("n_bins must be at least 2")
    a, p = _finite_pairs(actual_binary, predicted_probability)
    if np.any((a != 0) & (a != 1)):
        raise EvaluationError("actual_binary must contain only 0 or 1")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    rows: list[dict[str, Any]] = []
    for i in range(n_bins):
        low, high = edges[i], edges[i + 1]
        mask = (p >= low) & (p < high) if i < n_bins - 1 else (p >= low) & (p <= high)
        count = int(mask.sum())
        rows.append(
            {
                "bin_lower": round(float(low), 6),
                "bin_upper": round(float(high), 6),
                "count": count,
                "mean_predicted": round(float(p[mask].mean()), 6) if count else None,
                "observed_frequency": round(float(a[mask].mean()), 6) if count else None,
            }
        )
    return rows


def pinball_loss(
    actual: Sequence[float], predicted_quantile: Sequence[float], *, quantile: float
) -> float | None:
    """Quantile (pinball) loss (doc 9.4) for interval/quantile regression."""
    if not 0 < quantile < 1:
        raise EvaluationError("quantile must be in (0, 1)")
    a, p = _finite_pairs(actual, predicted_quantile)
    if a.size == 0:
        return None
    difference = a - p
    loss = np.where(difference >= 0, quantile * difference, (quantile - 1) * difference)
    return float(np.mean(loss))


def date_level_spearman_ic(
    frame: pd.DataFrame,
    *,
    score_column: str,
    outcome_column: str,
    date_column: str = "as_of_session",
    min_names_per_date: int = 5,
) -> pd.Series:
    """Per-DATE Spearman rank correlation between score and outcome (doc 11.4).

    Per-date, never pooled. This project's standing rule (memory:
    project_rigor_toolkit) is that pooled or row-level statistics are
    untrustworthy here -- pooling every (date, ticker) row treats names on
    the same day as independent observations when they share that day's
    market move, which massively overstates the sample size.

    Dates with fewer than `min_names_per_date` names are dropped: a rank
    correlation over 2-3 names is almost pure noise and would add variance
    while looking like signal.
    """
    for column in (score_column, outcome_column, date_column):
        if column not in frame.columns:
            raise EvaluationError(f"frame is missing column {column!r}")
    if min_names_per_date < 3:
        raise EvaluationError("min_names_per_date must be at least 3")

    values: dict[Any, float] = {}
    for date, group in frame.groupby(date_column, sort=True):
        usable = group[[score_column, outcome_column]].apply(
            pd.to_numeric, errors="coerce"
        ).replace([np.inf, -np.inf], np.nan).dropna()
        if len(usable) < min_names_per_date:
            continue
        if usable[score_column].nunique() < 2 or usable[outcome_column].nunique() < 2:
            continue
        correlation = usable[score_column].corr(
            usable[outcome_column], method="spearman"
        )
        if pd.notna(correlation):
            values[date] = float(correlation)
    return pd.Series(values, dtype=float).sort_index()


def summarize_information_coefficient(ic_by_date: pd.Series) -> dict[str, Any]:
    """IC mean, dispersion, and sign consistency (doc 11.4).

    Sign consistency is reported because a signal whose IC averages +0.03
    by flipping between +0.4 and -0.35 is a fundamentally different (and far
    less trustworthy) object than one that is weakly but persistently
    positive -- the mean alone hides that completely.
    """
    clean = pd.to_numeric(ic_by_date, errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    ).dropna()
    if clean.empty:
        return {
            "date_count": 0,
            "mean_ic": None,
            "std_ic": None,
            "positive_date_fraction": None,
            "information_ratio": None,
        }
    mean = float(clean.mean())
    std = float(clean.std(ddof=1)) if len(clean) > 1 else float("nan")
    return {
        "date_count": int(len(clean)),
        "mean_ic": round(mean, 6),
        "std_ic": round(std, 6) if math.isfinite(std) else None,
        "positive_date_fraction": round(float((clean > 0).mean()), 6),
        # IC "information ratio" = mean/std. Reported WITHOUT a p-value on
        # purpose: a t-statistic here would assume independent dates, which
        # overlapping forward-return windows violate. Use
        # backtest/engine.py's block bootstrap for actual significance.
        "information_ratio": (
            round(mean / std, 6) if math.isfinite(std) and std > 0 else None
        ),
    }


def top_minus_bottom_quantile_spread(
    frame: pd.DataFrame,
    *,
    score_column: str,
    outcome_column: str,
    date_column: str = "as_of_session",
    quantiles: int = 5,
    min_names_per_date: int = 5,
) -> dict[str, Any]:
    """Mean outcome of the top score quantile minus the bottom, per date
    then averaged (doc 11.4) -- again per-date, never pooled."""
    if quantiles < 2:
        raise EvaluationError("quantiles must be at least 2")
    for column in (score_column, outcome_column, date_column):
        if column not in frame.columns:
            raise EvaluationError(f"frame is missing column {column!r}")

    spreads: dict[Any, float] = {}
    for date, group in frame.groupby(date_column, sort=True):
        usable = group[[score_column, outcome_column]].apply(
            pd.to_numeric, errors="coerce"
        ).replace([np.inf, -np.inf], np.nan).dropna()
        if len(usable) < max(min_names_per_date, quantiles):
            continue
        ranked = usable[score_column].rank(method="first")
        try:
            buckets = pd.qcut(ranked, quantiles, labels=False, duplicates="drop")
        except ValueError:
            continue
        if pd.isna(buckets).all():
            continue
        top = usable.loc[buckets == buckets.max(), outcome_column]
        bottom = usable.loc[buckets == buckets.min(), outcome_column]
        if top.empty or bottom.empty:
            continue
        spreads[date] = float(top.mean() - bottom.mean())

    series = pd.Series(spreads, dtype=float).sort_index()
    if series.empty:
        return {"date_count": 0, "mean_spread": None, "positive_date_fraction": None}
    return {
        "date_count": int(len(series)),
        "mean_spread": round(float(series.mean()), 6),
        "positive_date_fraction": round(float((series > 0).mean()), 6),
    }


@dataclasses.dataclass(frozen=True)
class EvaluationReport:
    """The immutable evaluation-report contract (doc section 14).

    `verdict` is restricted to the doc's own vocabulary. Notably absent:
    anything resembling "promoted" or "production" -- doc 14 requires a
    separate, explicit registry decision, and doc 17 prohibits automatic
    promotion outright.
    """

    VERDICTS = ("rejected", "exploratory", "promising_unconfirmed", "confirmation_run_requested")

    research_question: str
    preregistered_primary_outcome: str
    candidate_models: tuple[str, ...]
    baselines: tuple[str, ...]
    simultaneous_research_looks: int
    dataset_hash: str
    feature_set_version: str
    point_in_time_data: bool
    survivorship_bias_note: str
    split_summary: tuple[Mapping[str, Any], ...]
    entry_timing: str
    cost_tax_capital_assumptions: Mapping[str, Any]
    fold_metrics: tuple[Mapping[str, Any], ...]
    aggregate_metrics: Mapping[str, Any]
    dependence_aware_uncertainty: Mapping[str, Any]
    failure_analysis: Mapping[str, Any]
    calibration: tuple[Mapping[str, Any], ...]
    coverage_warnings: tuple[str, ...]
    limitations: tuple[str, ...]
    verdict: str
    generated_at: str

    def __post_init__(self) -> None:
        if self.verdict not in self.VERDICTS:
            raise EvaluationError(
                f"verdict must be one of {self.VERDICTS}, got {self.verdict!r}"
            )
        if not self.baselines:
            raise EvaluationError(
                "an evaluation report must name at least one frozen baseline "
                "(doc 14.1: a result is not promising merely because one metric improved)"
            )
        if self.simultaneous_research_looks < 1:
            raise EvaluationError("simultaneous_research_looks must be at least 1")
        if not self.limitations:
            raise EvaluationError(
                "an evaluation report must state its limitations explicitly (doc 14)"
            )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "research_question": self.research_question,
            "preregistered_primary_outcome": self.preregistered_primary_outcome,
            "candidate_models": list(self.candidate_models),
            "baselines": list(self.baselines),
            "simultaneous_research_looks": self.simultaneous_research_looks,
            "dataset_hash": self.dataset_hash,
            "feature_set_version": self.feature_set_version,
            "point_in_time_data": self.point_in_time_data,
            "survivorship_bias_note": self.survivorship_bias_note,
            "split_summary": [dict(s) for s in self.split_summary],
            "entry_timing": self.entry_timing,
            "cost_tax_capital_assumptions": dict(self.cost_tax_capital_assumptions),
            "fold_metrics": [dict(m) for m in self.fold_metrics],
            "aggregate_metrics": dict(self.aggregate_metrics),
            "dependence_aware_uncertainty": dict(self.dependence_aware_uncertainty),
            "failure_analysis": dict(self.failure_analysis),
            "calibration": [dict(c) for c in self.calibration],
            "coverage_warnings": list(self.coverage_warnings),
            "limitations": list(self.limitations),
            "verdict": self.verdict,
            "generated_at": self.generated_at,
            "promotion_blockers": list(self.promotion_blockers()),
        }
        payload["report_sha256"] = hash_payload(payload)
        return payload

    def promotion_blockers(self) -> tuple[str, ...]:
        """Reasons this result may not be promoted, derived rather than
        asserted -- mirrors backtest/research_report.py's existing
        promotion_blockers list so both pipelines block for the same
        reasons in the same vocabulary."""
        blockers: list[str] = []
        if not self.point_in_time_data:
            blockers.append("not_point_in_time_data")
        if self.verdict != "promising_unconfirmed":
            blockers.append(f"verdict_is_{self.verdict}")
        if self.coverage_warnings:
            blockers.append("coverage_warnings_present")
        if len(self.fold_metrics) < 2:
            blockers.append("fewer_than_two_untouched_folds")
        return tuple(blockers)


def beats_baseline_in_multiple_folds(
    fold_metrics: Sequence[Mapping[str, Any]],
    *,
    candidate_key: str,
    baseline_key: str,
    lower_is_better: bool = True,
    minimum_folds: int = 2,
) -> dict[str, Any]:
    """Doc 14.1's first necessary condition: "beat its frozen simple
    baseline in more than one untouched walk-forward fold."

    Returns the count and the verdict rather than a bare bool, so a caller
    reporting this cannot hide HOW narrowly it passed. Note this is a
    NECESSARY, not sufficient, condition -- doc 14.1 is explicit about that.
    """
    wins = 0
    comparable = 0
    per_fold: list[dict[str, Any]] = []
    for index, metrics in enumerate(fold_metrics):
        candidate = metrics.get(candidate_key)
        baseline = metrics.get(baseline_key)
        if candidate is None or baseline is None:
            per_fold.append({"fold_index": index, "comparable": False, "won": False})
            continue
        candidate_value = float(candidate)
        baseline_value = float(baseline)
        if not (math.isfinite(candidate_value) and math.isfinite(baseline_value)):
            per_fold.append({"fold_index": index, "comparable": False, "won": False})
            continue
        comparable += 1
        won = (
            candidate_value < baseline_value
            if lower_is_better
            else candidate_value > baseline_value
        )
        wins += int(won)
        per_fold.append({"fold_index": index, "comparable": True, "won": bool(won)})
    return {
        "comparable_folds": comparable,
        "folds_won": wins,
        "minimum_folds_required": minimum_folds,
        "passes": comparable >= minimum_folds and wins >= minimum_folds,
        "per_fold": per_fold,
    }
