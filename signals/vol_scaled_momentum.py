"""
Volatility-scaled (risk-adjusted) momentum.

Plain cross-sectional momentum (signals/momentum.py) ranks stocks by
trailing return, which systematically hands the top of the ranking to
whichever names are simply the most volatile — a 40% run in a 60%-vol
stock is a far less remarkable event than the same run in a 15%-vol
stock, but raw ranking cannot tell them apart. Dividing each stock's
trailing return by its own recent realized volatility puts every name on
a comparable "moves per unit of risk" scale before ranking.

Construction (frozen 2026-08-03, before any result was observed):

  numerator   — 12-1 month total return: the return from 252 trading days
                ago to 21 trading days ago, skipping the most recent
                month to avoid short-term reversal contamination.
  denominator — annualized realized volatility of daily returns over the
                past 60 trading days (daily std * sqrt(252)).
  ranking     — cross-sectional each day; long the top quintile ("up"),
                bottom quintile emitted as "dip" for symmetry.

Note this deliberately uses a 252-day numerator (the 12-1 construction
the idea was specified with) rather than this project's existing
MOMENTUM_LOOKBACK_DAYS of 126 (a 6-1 construction). The two are
different bets on different horizons; reusing the 126 constant here
would have quietly tested something other than the stated idea.

`low_vol_only` implements the specified variant — take the signal only
when a stock's own volatility is below its trailing 1-year median. It
defaults to OFF: the base construction is the pre-specified test, and
the variant is a sensitivity check, not a second independent shot at
significance.

Same output column contract as scan_dips_and_ups(), so this plugs into
backtest/engine.py's tooling unchanged.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]

VOL_SCALED_LOOKBACK_DAYS = 252   # ~12 trading months
VOL_SCALED_SKIP_DAYS = 21        # skip the most recent ~month
VOL_SCALED_VOL_WINDOW = 60       # realized-vol estimation window
VOL_SCALED_TOP_PCT = 0.2
VOL_SCALED_BOTTOM_PCT = 0.2
VOL_SCALED_MEDIAN_WINDOW = 252   # 1-year median for the low_vol_only variant

TRADING_DAYS_PER_YEAR = 252


def scan_vol_scaled_momentum(
    data: dict[str, pd.DataFrame],
    as_of: pd.Timestamp | None = None,
    lookback_days: int = VOL_SCALED_LOOKBACK_DAYS,
    skip_days: int = VOL_SCALED_SKIP_DAYS,
    vol_window: int = VOL_SCALED_VOL_WINDOW,
    top_pct: float = VOL_SCALED_TOP_PCT,
    bottom_pct: float = VOL_SCALED_BOTTOM_PCT,
    low_vol_only: bool = False,
    median_window: int = VOL_SCALED_MEDIAN_WINDOW,
) -> pd.DataFrame:
    """
    Rank the universe by (12-1 month return / annualized realized vol)
    and flag the top `top_pct` as "up", the bottom `bottom_pct` as "dip".

    `return_pct` carries the raw 12-1 total return in percent (so the
    unscaled move stays inspectable), while `return_zscore` carries the
    CROSS-SECTIONAL z-score of the VOL-SCALED score — the quantity
    actually ranked on. `volume_zscore` is NaN; like every momentum
    variant here this is not gated on volume.

    Every input is trailing-only: the vol window ends at `as_of`, and the
    return window ends `skip_days` before it.
    """
    if lookback_days < 1:
        raise ValueError(f"lookback_days must be positive, got {lookback_days!r}.")
    if skip_days < 0:
        raise ValueError(f"skip_days must be non-negative, got {skip_days!r}.")
    if vol_window < 2:
        raise ValueError(f"vol_window must be at least 2, got {vol_window!r}.")

    scores: dict[str, float] = {}
    raw_returns: dict[str, float] = {}
    as_of_info: dict[str, tuple] = {}

    for ticker, df in data.items():
        if as_of is not None and as_of not in df.index:
            continue
        idx = df.index.get_loc(as_of) if as_of is not None else len(df) - 1

        start_idx = idx - skip_days - lookback_days
        end_idx = idx - skip_days
        if start_idx < 0 or end_idx < 0:
            continue  # not enough trailing history yet

        start_price = float(df["close"].iloc[start_idx])
        end_price = float(df["close"].iloc[end_idx])
        if start_price <= 0:
            continue

        total_return_pct = (end_price - start_price) / start_price * 100

        # Realized vol over the `vol_window` days ending AT as_of. The
        # slice starts at idx-vol_window so it holds vol_window returns
        # once pct_change drops the first row.
        window_start = idx - vol_window
        if window_start < 0:
            continue
        window_closes = df["close"].iloc[window_start : idx + 1]
        daily_returns = window_closes.pct_change().dropna()
        if len(daily_returns) < 2:
            continue
        daily_std = float(daily_returns.std())
        # A perfectly flat window gives zero risk and would make the
        # scaled score infinite — drop the name instead of letting it
        # take over the top of the ranking.
        if not np.isfinite(daily_std) or daily_std <= 0:
            continue
        annualized_vol = daily_std * np.sqrt(TRADING_DAYS_PER_YEAR)

        if low_vol_only:
            median_start = idx - median_window
            if median_start < 0:
                continue
            history = df["close"].iloc[median_start : idx + 1].pct_change().dropna()
            if len(history) < 2:
                continue
            rolling_vol = history.rolling(vol_window).std().dropna()
            if rolling_vol.empty:
                continue
            if daily_std >= float(rolling_vol.median()):
                continue  # own vol is not below its 1-year median

        score = total_return_pct / (annualized_vol * 100)
        if not np.isfinite(score):
            continue

        scores[ticker] = score
        raw_returns[ticker] = total_return_pct
        as_of_info[ticker] = (df.index[idx], float(df["close"].iloc[idx]))

    if len(scores) < 5:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    values = pd.Series(scores)
    mean, std = values.mean(), values.std()
    if std == 0 or pd.isna(std):
        return pd.DataFrame(columns=RESULT_COLUMNS)
    cross_sectional_z = (values - mean) / std

    n_top = max(1, int(len(values) * top_pct))
    n_bottom = max(1, int(len(values) * bottom_pct))
    ranked = values.sort_values(ascending=False)
    top_tickers = set(ranked.index[:n_top])
    bottom_tickers = set(ranked.index[-n_bottom:]) - top_tickers

    rows = []
    for ticker in top_tickers | bottom_tickers:
        date, close = as_of_info[ticker]
        rows.append(
            {
                "ticker": ticker,
                "date": date,
                "close": round(close, 2),
                "return_pct": round(raw_returns[ticker], 2),
                "return_zscore": round(float(cross_sectional_z[ticker]), 2),
                "volume_zscore": float("nan"),
                "direction": "up" if ticker in top_tickers else "dip",
            }
        )

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    result = pd.DataFrame(rows)
    return result.reindex(result["return_zscore"].abs().sort_values(ascending=False).index).reset_index(drop=True)
