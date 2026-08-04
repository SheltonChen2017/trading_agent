"""
Idiosyncratic volatility anomaly (Ang, Hodrick, Xing & Zhang, "The
Cross-Section of Volatility and Expected Returns", Journal of Finance
2006; replicated internationally in their 2009 follow-up).

The finding: stocks with HIGH recent idiosyncratic (residual, market-
model) volatility earn LOW average future returns, and vice versa -- the
opposite of what a simple risk-return tradeoff would predict, and one of
the more robust anomalies in the literature (survives controls for
trading frictions, information dissemination, and higher moments in
their original study).

REUSES signals/residual.py's causal market-model regression
(compute_residual_features / build_residual_frames) rather than
reimplementing beta estimation -- same trailing, shifted-by-one-row
regression, same look-ahead discipline. KNOWN LIMITATION: Ang et al.
estimate idiosyncratic volatility against the Fama-French 3-factor
model; this project only has a single-factor (SPY) market model, so this
is a market-model idiosyncratic-volatility proxy, not the exact FF3
construction. Treat this as a real but weaker version of the same idea.

Construction (frozen 2026-08-03, before any result was observed):

  idio_vol    = trailing daily std of `residual` (from
                compute_residual_features) over IDIO_VOL_WINDOW = 21
                trading days -- matching Ang et al.'s ~1-month formation
                window (they form portfolios monthly on the trailing
                month's daily idiosyncratic volatility)
  beta_window = 90 trading days (RESIDUAL_BETA_WINDOW, reused unchanged
                from signals/residual.py so the underlying regression
                means the same thing across every residual-based signal
                in this project)
  score       = -idio_vol (NEGATED so the ranking direction matches this
                project's convention: "up" = top of the ranked score =
                the well-evidenced bet. Since LOW idio vol predicts
                HIGH returns, ranking on -idio_vol puts the low-vol
                names at the top.)
  ranking     = cross-sectional each day; long the top quintile ("up" --
                lowest idiosyncratic volatility), bottom quintile
                emitted as "dip" for symmetry (highest idiosyncratic
                volatility -- the anomaly predicts THIS leg to
                underperform, so a positive "dip" edge would be evidence
                AGAINST the anomaly, not for it)
  hold        = 21 trading days (~1 month) -- matches Ang et al.'s
                monthly rebalance / one-month-forward-return
                construction exactly, not an arbitrary choice

DIRECTION SEMANTICS. "up" (long low-idio-vol names) is the studied,
well-evidenced bet. "dip" (long high-idio-vol names) is a control: the
anomaly predicts this leg should be a WEAK or NEGATIVE edge, not a
strong positive one -- a strong positive "dip" edge would contradict the
anomaly rather than confirm a second version of it.

Same output column contract as scan_dips_and_ups(). `return_zscore`
carries the CROSS-SECTIONAL z-score of the (negated) idio-vol score,
matching every other cross-sectional signal in this project.
`return_pct` carries the raw idio_vol itself (in percent, daily units --
NOT negated, so the raw magnitude stays inspectable). `volume_zscore` is
NaN; like every other cross-sectional signal here, this is not gated on
volume.
"""
from __future__ import annotations

import pandas as pd

from signals.residual import RESIDUAL_BETA_WINDOW, _resolve_frames

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]

IDIO_VOL_WINDOW = 21        # ~1 trading month, matches Ang et al.'s formation window
IDIO_VOL_TOP_PCT = 0.2
IDIO_VOL_BOTTOM_PCT = 0.2


def scan_idio_vol(
    data: dict[str, pd.DataFrame],
    as_of: pd.Timestamp | None = None,
    residual_frames: dict[str, pd.DataFrame] | None = None,
    benchmark_df: pd.DataFrame | None = None,
    idio_vol_window: int = IDIO_VOL_WINDOW,
    top_pct: float = IDIO_VOL_TOP_PCT,
    bottom_pct: float = IDIO_VOL_BOTTOM_PCT,
) -> pd.DataFrame:
    """
    Rank the universe by trailing idiosyncratic (residual) volatility and
    flag the LOWEST-idio-vol `top_pct` as "up" (the well-evidenced bet),
    the HIGHEST-idio-vol `bottom_pct` as "dip" (control). See module
    docstring for why the ranking score is negated idio_vol, not raw
    idio_vol.

    `residual_frames` must come from build_residual_frames() (built with
    RESIDUAL_BETA_WINDOW, this project's shared regression window) --
    pass it precomputed for speed exactly like scan_residual_momentum().
    """
    if idio_vol_window < 2:
        raise ValueError(f"idio_vol_window must be at least 2, got {idio_vol_window!r}.")

    frames = _resolve_frames(data, residual_frames, benchmark_df)

    idio_vol_by_ticker: dict[str, float] = {}
    as_of_info: dict[str, tuple] = {}

    for ticker, features in frames.items():
        if as_of is not None:
            if as_of not in features.index:
                continue
            idx = features.index.get_loc(as_of)
        else:
            idx = len(features) - 1

        start_idx = idx - idio_vol_window + 1
        if start_idx < 0:
            continue  # not enough trailing residual history yet

        window = features["residual"].iloc[start_idx : idx + 1]
        if window.isna().any():
            continue  # a gap in the residual series (e.g. benchmark hole) invalidates this window
        idio_vol = float(window.std())
        if not pd.notna(idio_vol) or idio_vol <= 0:
            continue

        idio_vol_by_ticker[ticker] = idio_vol
        as_of_info[ticker] = (features.index[idx], float(features["close"].iloc[idx]))

    if len(idio_vol_by_ticker) < 5:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    raw_values = pd.Series(idio_vol_by_ticker)
    scores = -raw_values  # negate: "up" = top of ranked score = LOWEST idio vol
    mean, std = scores.mean(), scores.std()
    if std == 0 or pd.isna(std):
        return pd.DataFrame(columns=RESULT_COLUMNS)
    cross_sectional_z = (scores - mean) / std

    n_top = max(1, int(len(scores) * top_pct))
    n_bottom = max(1, int(len(scores) * bottom_pct))
    ranked = scores.sort_values(ascending=False)
    top_tickers = set(ranked.index[:n_top])       # lowest idio vol
    bottom_tickers = set(ranked.index[-n_bottom:]) - top_tickers  # highest idio vol

    rows = []
    for ticker in top_tickers | bottom_tickers:
        date, close = as_of_info[ticker]
        rows.append(
            {
                "ticker": ticker,
                "date": date,
                "close": round(close, 2),
                "return_pct": round(raw_values[ticker] * 100, 2),
                "return_zscore": round(float(cross_sectional_z[ticker]), 2),
                "volume_zscore": float("nan"),
                "direction": "up" if ticker in top_tickers else "dip",
            }
        )

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    result = pd.DataFrame(rows)
    return result.reindex(result["return_zscore"].abs().sort_values(ascending=False).index).reset_index(drop=True)
