"""ML-3: latent-factor concentration analysis (strategy doc section 7).

This is a RISK-DESCRIPTION model, not an alpha signal. It answers "how many
genuinely independent bets is this portfolio actually making?" -- the
question that matters most for a technology-heavy book where several
positions can be one factor wearing different tickers.

Per doc 7.1, two baselines are computed BEFORE the PCA and reported
alongside it, so the latent-factor view can never be read in isolation:

  1. the project's existing pairwise-correlation clustering
     (assistant/risk_copilot.py's find_correlated_clusters -- reused, not
     reimplemented), and
  2. a Ledoit-Wolf shrinkage covariance estimate.

Factors are labeled mechanically ("Factor 1", "Factor 2"). Doc 7.1 is
explicit: "Never ask an LLM to invent factor meaning." A principal
component is a statistical axis, not a named economic theme, and putting a
confident label like "the AI trade" on it would manufacture an
interpretation the mathematics does not support.

The report contains no proposed trades and no target weights (doc 7.2).
"""
from __future__ import annotations

import dataclasses
import math
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

DEFAULT_LOOKBACK_SESSIONS = 252
DEFAULT_MIN_OBSERVATIONS = 60
# Cap on displayed factors regardless of explained variance (doc 7.1:
# "with a documented cap"). Beyond a handful, principal components of a
# ~10-30 name book are dominated by estimation noise, and displaying them
# invites over-reading.
MAX_DISPLAYED_FACTORS = 5
DEFAULT_EXPLAINED_VARIANCE_TARGET = 0.90


class FactorRiskError(ValueError):
    """Return data cannot support a trustworthy factor decomposition."""


@dataclasses.dataclass(frozen=True)
class FactorRiskReport:
    """Typed report contract (doc 7.2). Deliberately carries no trade
    proposal, target weight, or action field of any kind."""

    available: bool
    as_of: str | None
    tickers: tuple[str, ...]
    missing_tickers: tuple[str, ...]
    common_observation_count: int
    covariance_estimator: str
    lookback_sessions: int
    explained_variance_ratio: tuple[float, ...]
    cumulative_explained_variance: tuple[float, ...]
    displayed_factor_count: int
    loadings: Mapping[str, Mapping[str, float]]
    portfolio_factor_exposures: Mapping[str, float]
    factor_contribution_by_position: Mapping[str, Mapping[str, float]]
    residual_risk_by_position: Mapping[str, float]
    effective_independent_bets: float | None
    correlation_clusters: tuple[str, ...]
    shrinkage_baseline: Mapping[str, Any]
    warnings: tuple[str, ...]
    unavailable_reason: str | None = None

    @property
    def production_authoritative(self) -> bool:
        """Risk description is context only and can never authorize a trade."""
        return False

    @property
    def evidence_status(self) -> str:
        return "exploratory" if self.available else "unavailable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "evidence_status": self.evidence_status,
            "production_authoritative": self.production_authoritative,
            "as_of": self.as_of,
            "tickers": list(self.tickers),
            "missing_tickers": list(self.missing_tickers),
            "common_observation_count": self.common_observation_count,
            "covariance_estimator": self.covariance_estimator,
            "lookback_sessions": self.lookback_sessions,
            "explained_variance_ratio": list(self.explained_variance_ratio),
            "cumulative_explained_variance": list(self.cumulative_explained_variance),
            "displayed_factor_count": self.displayed_factor_count,
            "loadings": {k: dict(v) for k, v in self.loadings.items()},
            "portfolio_factor_exposures": dict(self.portfolio_factor_exposures),
            "factor_contribution_by_position": {
                k: dict(v) for k, v in self.factor_contribution_by_position.items()
            },
            "residual_risk_by_position": dict(self.residual_risk_by_position),
            "effective_independent_bets": self.effective_independent_bets,
            "correlation_clusters": list(self.correlation_clusters),
            "shrinkage_baseline": dict(self.shrinkage_baseline),
            "warnings": list(self.warnings),
            "unavailable_reason": self.unavailable_reason,
        }


def _unavailable(reason: str, *, warnings: Sequence[str] = ()) -> FactorRiskReport:
    """Doc 3.3: an unavailable result must be operationally equivalent to no
    model -- never a default, confident-looking one."""
    return FactorRiskReport(
        available=False,
        as_of=None,
        tickers=(),
        missing_tickers=(),
        common_observation_count=0,
        covariance_estimator="none",
        lookback_sessions=0,
        explained_variance_ratio=(),
        cumulative_explained_variance=(),
        displayed_factor_count=0,
        loadings={},
        portfolio_factor_exposures={},
        factor_contribution_by_position={},
        residual_risk_by_position={},
        effective_independent_bets=None,
        correlation_clusters=(),
        shrinkage_baseline={},
        warnings=tuple(warnings),
        unavailable_reason=reason,
    )


def _align_returns(
    close_by_ticker: Mapping[str, pd.Series], lookback_sessions: int
) -> tuple[pd.DataFrame, tuple[str, ...], list[str]]:
    """Align every ticker on the SAME sessions before any covariance is
    computed. A ticker with insufficient common history is reported as
    missing, never silently backfilled or treated as zero-variance --
    the same discipline assistant/risk_copilot.py's
    portfolio_risk_decomposition() already applies."""
    warnings: list[str] = []
    usable: dict[str, pd.Series] = {}
    missing: list[str] = []
    for ticker, series in close_by_ticker.items():
        numeric = pd.to_numeric(series, errors="coerce")
        numeric = numeric.where(numeric > 0)
        if numeric.dropna().shape[0] < 2:
            missing.append(ticker)
            warnings.append(f"{ticker}: fewer than 2 usable closes")
            continue
        usable[ticker] = numeric
    if not usable:
        return pd.DataFrame(), (), warnings

    # sort_index(axis=1): column order must come from the TICKER NAMES, not
    # from the caller's dict insertion order. PCA loadings are per-column, so
    # an input-order-dependent column layout would make two runs over the
    # same portfolio produce differently-ordered (and, after sign
    # orientation, differently-signed) loadings -- doc 7.3 requires results
    # "invariant to input ticker order apart from display ordering".
    frame = pd.DataFrame(usable).sort_index().sort_index(axis=1)
    returns = frame.pct_change(fill_method=None)
    # Inner-join on sessions where EVERY remaining ticker has a finite
    # return -- explicit alignment, per doc 7.3's "mismatched histories
    # align before calculation".
    aligned = returns.dropna(how="any")
    if lookback_sessions > 0:
        aligned = aligned.tail(lookback_sessions)
    return aligned, tuple(sorted(usable)), warnings


def _effective_independent_bets(explained_variance_ratio: np.ndarray) -> float:
    """Inverse Herfindahl of the explained-variance shares.

    1.0 means every position moves as one factor (no diversification);
    N means N equally-sized independent risk sources. This is a standard
    'effective number of bets' construction, reported as a descriptive
    statistic -- it is not a target to optimize and carries no threshold.
    """
    shares = explained_variance_ratio / explained_variance_ratio.sum()
    return float(1.0 / np.sum(np.square(shares)))


def _orient_components_deterministically(components: np.ndarray) -> np.ndarray:
    """Fix each component's sign so repeated runs are byte-identical.

    PCA components are only defined up to sign: an eigensolver may return
    v or -v for the same data, which would make loadings flip between runs
    and any stored/compared report spuriously "change". Convention here:
    the entry with the largest absolute value is forced positive, with the
    lowest-index entry winning an exact tie (doc 7.1/7.3: "orient component
    signs deterministically").
    """
    oriented = components.copy()
    for row in range(oriented.shape[0]):
        vector = oriented[row]
        dominant = int(np.argmax(np.abs(vector)))
        if vector[dominant] < 0:
            oriented[row] = -vector
    return oriented


def _shrinkage_baseline(returns: pd.DataFrame) -> dict[str, Any]:
    """Baseline #2 (doc 7.1): Ledoit-Wolf shrinkage covariance.

    Reported as its own baseline rather than fed into the PCA: the point is
    to show whether the sample covariance the PCA runs on is itself
    unstable. A high shrinkage coefficient means the sample covariance was
    heavily pulled toward a diagonal target, which is a direct warning that
    the latent-factor structure below is estimated from thin data.
    """
    from sklearn.covariance import LedoitWolf

    estimator = LedoitWolf().fit(returns.to_numpy(dtype=float))
    covariance = estimator.covariance_
    variances = np.diag(covariance)
    return {
        "estimator": "sklearn.covariance.LedoitWolf",
        "shrinkage_coefficient": round(float(estimator.shrinkage_), 6),
        "mean_pairwise_correlation": round(
            float(_mean_offdiagonal_correlation(covariance)), 6
        ),
        "annualized_volatility_pct_by_ticker": {
            ticker: round(float(np.sqrt(variance) * np.sqrt(252) * 100), 6)
            for ticker, variance in zip(returns.columns, variances)
        },
    }


def _mean_offdiagonal_correlation(covariance: np.ndarray) -> float:
    deviations = np.sqrt(np.diag(covariance))
    if not np.all(deviations > 0):
        return float("nan")
    correlation = covariance / np.outer(deviations, deviations)
    n = correlation.shape[0]
    if n < 2:
        return float("nan")
    off_diagonal = correlation[~np.eye(n, dtype=bool)]
    return float(np.mean(off_diagonal))


def compute_factor_concentration_report(
    close_by_ticker: Mapping[str, pd.Series],
    weights: Mapping[str, float],
    *,
    lookback_sessions: int = DEFAULT_LOOKBACK_SESSIONS,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
    explained_variance_target: float = DEFAULT_EXPLAINED_VARIANCE_TARGET,
    correlation_clusters: Sequence[str] = (),
) -> FactorRiskReport:
    """PCA-based concentration report with both doc-7.1 baselines attached.

    `weights` are portfolio weights (fractions of equity) keyed by ticker;
    they are used only to project EXISTING exposure onto the factors. No
    target weight is ever produced. `correlation_clusters` is the caller's
    already-computed output from assistant/risk_copilot.py's
    find_correlated_clusters() -- passed in rather than imported so this
    research module keeps zero dependency on the assistant package (the
    ml-import boundary runs the other way, but keeping ml/ free of
    assistant/ imports also keeps this usable from a bare research script).
    """
    if (
        isinstance(min_observations, bool)
        or not isinstance(min_observations, int)
        or min_observations < 20
    ):
        raise FactorRiskError("min_observations must be an integer >= 20")
    if (
        isinstance(lookback_sessions, bool)
        or not isinstance(lookback_sessions, int)
        or lookback_sessions < min_observations
    ):
        raise FactorRiskError("lookback_sessions must be an integer >= min_observations")
    if (
        isinstance(explained_variance_target, bool)
        or not isinstance(explained_variance_target, (int, float))
        or not 0 < float(explained_variance_target) <= 1
    ):
        raise FactorRiskError("explained_variance_target must be in (0, 1]")
    if not close_by_ticker:
        return _unavailable("no price series supplied")

    aligned, usable_tickers, warnings = _align_returns(close_by_ticker, lookback_sessions)
    requested = tuple(sorted(close_by_ticker))
    missing = tuple(t for t in requested if t not in usable_tickers)

    if aligned.empty or aligned.shape[1] < 2:
        return _unavailable(
            "fewer than 2 tickers have usable aligned return history",
            warnings=warnings,
        )
    if aligned.shape[0] < min_observations:
        return _unavailable(
            f"only {aligned.shape[0]} common observations; {min_observations} required",
            warnings=warnings,
        )
    values = aligned.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        # Doc 7.3: "NaN and infinity never produce a successful report."
        return _unavailable(
            "aligned returns contain non-finite values", warnings=warnings
        )

    standard_deviations = values.std(axis=0, ddof=1)
    constant_columns = [
        ticker
        for ticker, deviation in zip(aligned.columns, standard_deviations)
        if not math.isfinite(float(deviation)) or float(deviation) <= 0
    ]
    if constant_columns:
        # A constant series has no variance to decompose; standardizing it
        # would divide by zero and silently produce NaN loadings.
        return _unavailable(
            f"constant or zero-variance return series: {sorted(constant_columns)}",
            warnings=warnings,
        )

    # Standardize using WINDOW-LOCAL statistics only (doc 7.1). This is a
    # descriptive decomposition of one window, not a fitted predictor, so
    # there is no train/test split to respect -- but the statistics must
    # still come from the same window being described, never a global one.
    standardized = (values - values.mean(axis=0)) / standard_deviations

    from sklearn.decomposition import PCA

    max_components = min(standardized.shape[0], standardized.shape[1])
    pca = PCA(n_components=max_components, svd_solver="full", random_state=0)
    pca.fit(standardized)
    explained = np.asarray(pca.explained_variance_ratio_, dtype=float)
    eigenvalues = np.asarray(pca.explained_variance_, dtype=float)
    cumulative = np.cumsum(explained)
    components = _orient_components_deterministically(np.asarray(pca.components_, dtype=float))
    # PCA's components_ are unit eigenvectors, not factor loadings.  For
    # standardized inputs the economically interpretable loading is
    # eigenvector * sqrt(eigenvalue): its square is the share of that
    # position's standardized variance explained by the factor.
    factor_loadings = components * np.sqrt(eigenvalues)[:, np.newaxis]

    reached_target = int(np.searchsorted(cumulative, explained_variance_target) + 1)
    displayed = max(1, min(reached_target, MAX_DISPLAYED_FACTORS, len(explained)))
    if reached_target > MAX_DISPLAYED_FACTORS:
        warnings.append(
            f"{reached_target} factors are needed to reach "
            f"{explained_variance_target:.0%} explained variance; display is capped "
            f"at {MAX_DISPLAYED_FACTORS}"
        )

    tickers = tuple(str(c) for c in aligned.columns)
    factor_names = tuple(f"Factor {i + 1}" for i in range(displayed))

    loadings: dict[str, dict[str, float]] = {}
    for factor_index, factor_name in enumerate(factor_names):
        loadings[factor_name] = {
            ticker: round(float(factor_loadings[factor_index, ticker_index]), 6)
            for ticker_index, ticker in enumerate(tickers)
        }

    weight_vector = np.array(
        [float(weights.get(ticker, 0.0)) for ticker in tickers], dtype=float
    )
    if not np.isfinite(weight_vector).all():
        return _unavailable("weights contain non-finite values", warnings=warnings)

    portfolio_exposures: dict[str, float] = {}
    contribution_by_position: dict[str, dict[str, float]] = {
        ticker: {} for ticker in tickers
    }
    for factor_index, factor_name in enumerate(factor_names):
        loading = factor_loadings[factor_index]
        exposure = float(np.dot(weight_vector, loading))
        portfolio_exposures[factor_name] = round(exposure, 6)
        for ticker_index, ticker in enumerate(tickers):
            contribution_by_position[ticker][factor_name] = round(
                float(weight_vector[ticker_index] * loading[ticker_index]), 6
            )

    # Residual risk: the share of each position's standardized variance NOT
    # captured by the displayed factors. 1.0 means the position is entirely
    # idiosyncratic relative to what is displayed; 0.0 means fully explained.
    displayed_loadings = factor_loadings[:displayed]
    explained_share_by_ticker = np.sum(np.square(displayed_loadings), axis=0)
    residual_by_position = {
        ticker: round(float(max(0.0, 1.0 - explained_share_by_ticker[i])), 6)
        for i, ticker in enumerate(tickers)
    }

    effective_bets = _effective_independent_bets(explained)
    if len(tickers) < 3:
        warnings.append(
            "fewer than 3 aligned tickers: the factor decomposition is "
            "arithmetically valid but not economically informative"
        )

    return FactorRiskReport(
        available=True,
        as_of=str(aligned.index[-1].date())
        if isinstance(aligned.index, pd.DatetimeIndex)
        else str(aligned.index[-1]),
        tickers=tickers,
        missing_tickers=missing,
        common_observation_count=int(aligned.shape[0]),
        covariance_estimator="pca_on_window_standardized_returns",
        lookback_sessions=lookback_sessions,
        explained_variance_ratio=tuple(round(float(v), 6) for v in explained),
        cumulative_explained_variance=tuple(round(float(v), 6) for v in cumulative),
        displayed_factor_count=displayed,
        loadings=loadings,
        portfolio_factor_exposures=portfolio_exposures,
        factor_contribution_by_position=contribution_by_position,
        residual_risk_by_position=residual_by_position,
        effective_independent_bets=round(effective_bets, 6),
        correlation_clusters=tuple(correlation_clusters),
        shrinkage_baseline=_shrinkage_baseline(aligned),
        warnings=tuple(warnings),
    )
