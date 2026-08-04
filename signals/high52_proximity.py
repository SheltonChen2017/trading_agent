"""
52-week-high proximity signal (George & Hwang, "The 52-Week High and
Momentum Investing", Journal of Finance 2004).

DISTINCT FROM signals/breakout.py. Breakout is a discrete EVENT trigger:
"today's close IS a new N-day high/low, confirmed by volume." This
signal is a continuous CROSS-SECTIONAL RANK: how close is today's close
to its trailing 52-week high, for every stock, every day -- regardless
of whether anyone made a new high today. George & Hwang's finding is
that this nearness ratio predicts returns better than (and largely
subsumes) plain 6-1/12-1 momentum, and -- unlike raw momentum -- the
predicted returns do NOT reverse in the long run. It has since been
replicated in 18 of 20 major international markets.

Construction (frozen 2026-08-03, before any result was observed):

  score       = close / rolling_max(close, 252 trading days)
                (252 = BREAKOUT_LOOKBACK_DAYS, this project's existing
                52-week constant -- reused rather than re-specified so
                the "52-week" window means the same thing everywhere)
  ranking     = cross-sectional each day; long the top quintile ("up" --
                nearest to its 52-week high), bottom quintile emitted as
                "dip" for symmetry
  hold        = 126 trading days (~6 months) -- the SHORTER of the two
                published holding periods in George & Hwang (6 or 12
                months), chosen as the more conservative/testable of the
                two published numbers rather than an arbitrary midpoint

DIRECTION SEMANTICS. Only the "up" leg (long stocks near their 52-week
high) tests the George & Hwang hypothesis. The "dip" leg -- stocks far
below their 52-week high -- is not a studied bet in the momentum
literature; going long it would be closer to a deep-value/mean-reversion
bet the paper doesn't make. Read "dip" results as a control, not a
second hypothesis.

Same output column contract as scan_dips_and_ups(). `return_zscore`
carries the CROSS-SECTIONAL z-score of the proximity score (this ticker
vs the universe that day), matching signals/momentum.py's convention.
`volume_zscore` is NaN -- like every cross-sectional momentum variant in
this project, this signal is not gated on volume confirmation.
"""
from __future__ import annotations

import pandas as pd

from config import BREAKOUT_LOOKBACK_DAYS

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]

HIGH52_LOOKBACK_DAYS = BREAKOUT_LOOKBACK_DAYS  # 252 trading days, ~52 weeks
HIGH52_TOP_PCT = 0.2
HIGH52_BOTTOM_PCT = 0.2


def scan_high52_proximity(
    data: dict[str, pd.DataFrame],
    as_of: pd.Timestamp | None = None,
    lookback_days: int = HIGH52_LOOKBACK_DAYS,
    top_pct: float = HIGH52_TOP_PCT,
    bottom_pct: float = HIGH52_BOTTOM_PCT,
) -> pd.DataFrame:
    """
    Rank the universe by (close / trailing lookback_days-day high) and
    flag the top `top_pct` as "up" (nearest to the high), the bottom
    `bottom_pct` as "dip" (furthest below it).

    The rolling high at row t is computed over data up to and including
    row t (today's own close CAN be today's high -- that is the
    intended, causal definition of "how close is price to its 52-week
    high right now", not a look-ahead: nothing after `as_of` is used).
    """
    if lookback_days < 2:
        raise ValueError(f"lookback_days must be at least 2, got {lookback_days!r}.")

    scores: dict[str, float] = {}
    as_of_info: dict[str, tuple] = {}

    for ticker, df in data.items():
        if as_of is not None and as_of not in df.index:
            continue
        idx = df.index.get_loc(as_of) if as_of is not None else len(df) - 1

        start_idx = idx - lookback_days + 1
        if start_idx < 0:
            continue  # not enough trailing history for a full window yet

        window = df["close"].iloc[start_idx : idx + 1]
        rolling_high = float(window.max())
        close = float(df["close"].iloc[idx])
        if rolling_high <= 0:
            continue

        scores[ticker] = close / rolling_high
        as_of_info[ticker] = (df.index[idx], close)

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
                "return_pct": round(scores[ticker] * 100, 2),
                "return_zscore": round(float(cross_sectional_z[ticker]), 2),
                "volume_zscore": float("nan"),
                "direction": "up" if ticker in top_tickers else "dip",
            }
        )

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    result = pd.DataFrame(rows)
    return result.reindex(result["return_zscore"].abs().sort_values(ascending=False).index).reset_index(drop=True)
