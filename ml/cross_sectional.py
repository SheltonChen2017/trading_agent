"""ML-7: benchmark-relative cross-sectional ranker RESEARCH (strategy doc
section 11).

Doc 11's opening constraint: "Do not begin this phase until ML-1 through
ML-4 are stable." Those exist now. Its closing constraint is equally
binding and permanent: "No proposal adapter belongs in ML-7." This module
produces research metrics and typed observations only.

Two things here are deliberately NOT reimplemented, because this project
already owns better versions and its own standing rule (memory:
project_rigor_toolkit) is to distrust any freshly-written significance
code:

  * dependence-aware significance -> backtest/engine.py's
    bootstrap_edge_significance_by_block / out_of_sample_significance_by_block
  * multiplicity correction -> backtest/engine.py's bonferroni_threshold

`count_research_looks()` exists because doc 11.1 warns that even choosing
between QQQ and SOXX "is two research looks and must be counted in
multiplicity correction" -- the kind of silent look-inflation that makes a
p-value meaningless.
"""
from __future__ import annotations

import dataclasses
import math
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from backtest.engine import bonferroni_threshold, bootstrap_edge_significance_by_block
from ml.evaluation import (
    date_level_spearman_ic,
    summarize_information_coefficient,
    top_minus_bottom_quantile_spread,
)

MIN_NAMES_PER_DATE = 5
MIN_TRAINING_ROWS = 200


class RankerError(ValueError):
    """Inputs cannot support cross-sectional ranker research."""


@dataclasses.dataclass(frozen=True)
class RankerObservation:
    """Doc 11.5's output shape. No side, size, or action field."""

    ticker: str
    as_of_session: str
    horizon_sessions: int
    expected_excess_return_pct: float | None
    probability_positive_excess: float | None
    cross_sectional_percentile: float | None
    uncertainty: str
    model_key: str
    evidence_status: str

    @property
    def production_authoritative(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "as_of_session": self.as_of_session,
            "horizon_sessions": self.horizon_sessions,
            "expected_excess_return_pct": self.expected_excess_return_pct,
            "probability_positive_excess": self.probability_positive_excess,
            "cross_sectional_percentile": self.cross_sectional_percentile,
            "uncertainty": self.uncertainty,
            "model_key": self.model_key,
            "evidence_status": self.evidence_status,
            "production_authoritative": self.production_authoritative,
        }


def count_research_looks(
    *,
    models: Sequence[str],
    labels: Sequence[str],
    benchmarks: Sequence[str],
    horizons: Sequence[int],
    feature_families: Sequence[str],
) -> dict[str, Any]:
    """Count EVERY variant examined, not just the one being reported.

    Doc 11.4 requires "correction for every model, label, benchmark,
    horizon, and feature-family variant examined". The product is what
    matters: trying 4 models x 2 benchmarks x 3 horizons is 24 looks, and
    reporting the best of them at p<0.05 uncorrected is how a pure-noise
    result gets published. Returns the Bonferroni threshold from this
    project's existing implementation.
    """
    counts = {
        "models": len(models),
        "labels": len(labels),
        "benchmarks": len(benchmarks),
        "horizons": len(horizons),
        "feature_families": len(feature_families),
    }
    for name, value in counts.items():
        if value < 1:
            raise RankerError(f"{name} must contain at least one entry")
    total = 1
    for value in counts.values():
        total *= value
    return {
        "counts": counts,
        "total_research_looks": total,
        "bonferroni_alpha_threshold": bonferroni_threshold(total),
        "note": (
            "Every variant EXAMINED counts, including ones discarded after "
            "looking at their results (doc 11.1: selecting between QQQ and "
            "SOXX after seeing both is two looks, not one)."
        ),
    }


def fit_elastic_net_ranker(
    x_train: np.ndarray, y_train: np.ndarray, *, alpha: float = 0.01,
    l1_ratio: float = 0.5, random_seed: int = 0,
):
    """Doc 11.3 model #3: pooled elastic-net regression.

    POOLED across the cross-section, never one model per ticker -- doc 11.3:
    "Do not train one model per ticker." A per-ticker model on this
    project's sample size would fit a few dozen observations per name and
    memorize noise.
    """
    from sklearn.linear_model import ElasticNet

    if x_train.shape[0] < MIN_TRAINING_ROWS:
        raise RankerError(
            f"need at least {MIN_TRAINING_ROWS} pooled training rows, got {x_train.shape[0]}"
        )
    model = ElasticNet(alpha=alpha, l1_ratio=l1_ratio, random_state=random_seed, max_iter=5000)
    model.fit(x_train, y_train)
    return model


def fit_gradient_boosted_ranker(
    x_train: np.ndarray, y_train: np.ndarray, *, random_seed: int = 0, max_iter: int = 200
):
    """Doc 11.3 model #4: histogram gradient boosting, pooled."""
    from sklearn.ensemble import HistGradientBoostingRegressor

    if x_train.shape[0] < MIN_TRAINING_ROWS:
        raise RankerError(
            f"need at least {MIN_TRAINING_ROWS} pooled training rows, got {x_train.shape[0]}"
        )
    model = HistGradientBoostingRegressor(
        random_state=random_seed, max_iter=max_iter, early_stopping=False
    )
    model.fit(x_train, y_train)
    return model


def evaluate_ranker_fold(
    validation_frame: pd.DataFrame,
    *,
    score_column: str,
    outcome_column: str,
    date_column: str = "as_of_session",
    quantiles: int = 5,
) -> dict[str, Any]:
    """Date-level IC, IC summary, and quantile spread for one fold (doc 11.4)."""
    ic = date_level_spearman_ic(
        validation_frame,
        score_column=score_column,
        outcome_column=outcome_column,
        date_column=date_column,
        min_names_per_date=MIN_NAMES_PER_DATE,
    )
    summary = summarize_information_coefficient(ic)
    spread = top_minus_bottom_quantile_spread(
        validation_frame,
        score_column=score_column,
        outcome_column=outcome_column,
        date_column=date_column,
        quantiles=quantiles,
        min_names_per_date=MIN_NAMES_PER_DATE,
    )
    return {
        "information_coefficient": summary,
        "quantile_spread": spread,
        "ic_by_date": {str(k): round(float(v), 6) for k, v in ic.items()},
    }


def block_bootstrap_ic_significance(
    ic_by_date: pd.Series, *, block_length: int, n_bootstrap: int = 2000, seed: int = 0
) -> dict[str, Any]:
    """Dependence-aware significance via this project's EXISTING toolkit.

    Delegates to backtest/engine.py's bootstrap_edge_significance_by_block
    rather than writing a new bootstrap. That function already handles the
    circular moving-block resampling, the refusal conditions for too-few
    dates, and the minimum-detectable-effect reporting this project learned
    to require the hard way.

    `block_length` should be at least the label's horizon -- overlapping
    forward-return windows are the most direct source of the serial
    dependence a by-date-only bootstrap misses.
    """
    clean = pd.to_numeric(ic_by_date, errors="coerce").dropna()
    if clean.empty:
        return {"available": False, "reason": "no usable IC observations"}
    dates = pd.Series(list(clean.index), name="date")
    values = pd.Series(clean.to_numpy(dtype=float), name="ic")
    result = bootstrap_edge_significance_by_block(
        values, dates, block_length=block_length, n_bootstrap=n_bootstrap, seed=seed
    )
    return {"available": True, "block_length": block_length, **result}


def build_ranker_observations(
    frame: pd.DataFrame,
    *,
    score_column: str,
    model_key: str,
    horizon_sessions: int,
    date_column: str = "as_of_session",
    ticker_column: str = "ticker",
    evidence_status: str = "exploratory",
) -> tuple[RankerObservation, ...]:
    """Turn per-row scores into doc-11.5 observations.

    `uncertainty` is reported as a coarse label ("high" everywhere until a
    confirmed, calibrated result exists) rather than a fabricated numeric
    confidence -- doc 16 forbids presenting a raw model output as
    confidence without measured calibration, and no such measurement
    exists for any model in this repository.
    """
    for column in (score_column, date_column, ticker_column):
        if column not in frame.columns:
            raise RankerError(f"frame is missing column {column!r}")

    observations: list[RankerObservation] = []
    for date, group in frame.groupby(date_column, sort=True):
        scores = pd.to_numeric(group[score_column], errors="coerce")
        percentiles = scores.rank(pct=True)
        for (_, row), score, percentile in zip(group.iterrows(), scores, percentiles):
            observations.append(
                RankerObservation(
                    ticker=str(row[ticker_column]),
                    as_of_session=str(date),
                    horizon_sessions=horizon_sessions,
                    expected_excess_return_pct=(
                        round(float(score), 6) if pd.notna(score) else None
                    ),
                    probability_positive_excess=None,
                    cross_sectional_percentile=(
                        round(float(percentile), 6) if pd.notna(percentile) else None
                    ),
                    uncertainty="high",
                    model_key=model_key,
                    evidence_status=evidence_status,
                )
            )
    return tuple(observations)
