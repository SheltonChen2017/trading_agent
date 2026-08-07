"""
Cross-sectional momentum signal.

Academic momentum (Jegadeesh & Titman 1993, replicated many times since):
rank stocks by trailing return over a lookback window (here ~6 months),
skipping the most recent month to avoid short-term reversal contamination
(the classic "12-1 month" construction), and go long the top decile —
winners have historically tended to keep winning over the next 1-3
months. This is one of the most replicated anomalies in finance, and a
meaningfully different bet than signals/scanner.py's original signal: a
slower, CROSS-SECTIONAL ranking (compare stocks to EACH OTHER on a given
day) rather than a single-stock, absolute z-score-vs-own-history signal.

The "up" leg (long the winners) is the well-evidenced half of this trade.
The "dip" leg (bottom-decile losers) is included only for symmetry with
the rest of this project's dip/up structure — academically, betting
AGAINST the biggest losers (i.e. shorting them, or at least not going
long them) is the more commonly supported position, so treat any "dip"
signal from this scanner with extra skepticism.

Same output column contract as scan_dips_and_ups() (ticker, date, close,
return_pct, return_zscore, volume_zscore, direction), so this plugs into
every backtest/baseline/market/out-of-sample/significance tool in
backtest/engine.py unchanged — pass scan_fn=scan_momentum (with
scan_kwargs for any of the parameters below) to any of them.
"""
from __future__ import annotations

import pandas as pd

from config import (
    MOMENTUM_BOTTOM_PCT,
    MOMENTUM_LOOKBACK_DAYS,
    MOMENTUM_SKIP_DAYS,
    MOMENTUM_TOP_PCT,
)

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]


def scan_momentum(
    data: dict[str, pd.DataFrame],
    as_of: pd.Timestamp | None = None,
    lookback_days: int = MOMENTUM_LOOKBACK_DAYS,
    skip_days: int = MOMENTUM_SKIP_DAYS,
    top_pct: float = MOMENTUM_TOP_PCT,
    bottom_pct: float = MOMENTUM_BOTTOM_PCT,
) -> pd.DataFrame:
    """
    Rank every ticker in `data` by its trailing return over
    [as_of - skip_days - lookback_days, as_of - skip_days], then flag the
    top `top_pct` fraction as "up" (long momentum continuation) and
    bottom `bottom_pct` fraction as "dip" (see module docstring caveat).

    `return_zscore` in the output is the CROSS-SECTIONAL z-score of that
    ticker's momentum return relative to the whole universe that day —
    NOT a z-score of daily return vs. the stock's own history like
    scan_dips_and_ups — reported in the same field for pipeline
    compatibility. `volume_zscore` is left as NaN; momentum isn't gated
    on a volume confirmation the way the original scanner is.
    """
    momentum_returns: dict[str, float] = {}
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

        momentum_returns[ticker] = (end_price - start_price) / start_price * 100
        as_of_info[ticker] = (df.index[idx], float(df["close"].iloc[idx]))

    if len(momentum_returns) < 5:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    returns_series = pd.Series(momentum_returns)
    mean, std = returns_series.mean(), returns_series.std()
    if std == 0 or pd.isna(std):
        return pd.DataFrame(columns=RESULT_COLUMNS)
    cross_sectional_z = (returns_series - mean) / std

    n_top = max(1, int(len(returns_series) * top_pct))
    n_bottom = max(1, int(len(returns_series) * bottom_pct))
    ranked = returns_series.sort_values(ascending=False)
    top_tickers = set(ranked.index[:n_top])
    bottom_tickers = set(ranked.index[-n_bottom:])

    rows = []
    for ticker in top_tickers | bottom_tickers:
        date, close = as_of_info[ticker]
        rows.append(
            {
                "ticker": ticker,
                "date": date,
                "close": round(close, 2),
                "return_pct": round(momentum_returns[ticker], 2),
                "return_zscore": round(float(cross_sectional_z[ticker]), 2),
                "volume_zscore": float("nan"),
                "direction": "up" if ticker in top_tickers else "dip",
            }
        )

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    result = pd.DataFrame(rows)
    return result.reindex(result["return_zscore"].abs().sort_values(ascending=False).index).reset_index(drop=True)
