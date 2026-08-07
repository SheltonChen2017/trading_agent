"""
Fundamentals / earnings-growth signal.

Flags a stock on its earnings disclosure date when YoY reported EPS
growth (this quarter's EPS vs. the SAME quarter one year — 4 reports —
earlier) exceeds a threshold in either direction. A basic quality/growth
factor: real, documented investing style (growth investing broadly, and
earnings-growth screens specifically), distinct from every other signal
in this project, which are all pure price/volume technicals.

WHY THIS ISN'T BUILT FROM TODAY'S LIVE FUNDAMENTALS (yfinance's
Ticker.info snapshot, or quarterly_income_stmt): those only give a
CURRENT snapshot with no real point-in-time history — applying today's
P/E or growth figures to a backtest on past dates would be severe
look-ahead bias (the market didn't know today's numbers back then).
This signal instead reuses data/earnings_data.py's `reported_eps`
history, indexed by each figure's actual disclosure date
(`effective_date`), so at every point in the backtest only genuinely
already-known numbers are used — the same causal discipline every other
signal in this project follows.

Same output column contract as scan_dips_and_ups(), with `return_zscore`
repurposed as YoY EPS growth % (a stock's own trailing daily-return
z-score isn't the relevant concept here). Event-driven like PEAD — same
usage pattern (bind `earnings_data` with functools.partial) and the same
data-thinness caveat: yfinance's free earnings history gives ~20+
quarters for large caps, but that's still only ~4 events/ticker/year,
and a YoY comparison additionally needs 4 PRIOR quarters of history
before the first signal can even fire, shrinking the usable window
further.

    from functools import partial
    from data.earnings_data import fetch_earnings_history
    from signals.fundamentals import scan_fundamentals

    earnings = fetch_earnings_history(list(data.keys()))
    run_backtest(data, scan_fn=partial(scan_fundamentals, earnings_data=earnings), scan_kwargs={})
"""
from __future__ import annotations

import pandas as pd

from config import FUNDAMENTALS_GROWTH_THRESHOLD_PCT
from data.earnings_data import match_effective_date

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]
QUARTERS_PER_YEAR = 4


def scan_fundamentals(
    data: dict[str, pd.DataFrame],
    earnings_data: dict[str, pd.DataFrame],
    as_of: pd.Timestamp | None = None,
    growth_threshold_pct: float = FUNDAMENTALS_GROWTH_THRESHOLD_PCT,
) -> pd.DataFrame:
    """
    Flag a stock on its earnings disclosure date if YoY reported EPS
    growth exceeds `growth_threshold_pct` in either direction. Requires
    `earnings_data` (from data.earnings_data.fetch_earnings_history(),
    with a `reported_eps` column) and at least 4 prior quarters of
    history for that ticker to compute a YoY comparison at all.
    """
    if as_of is None:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    rows = []
    for ticker, price_df in data.items():
        if ticker not in earnings_data or as_of not in price_df.index:
            continue

        eps_history = earnings_data[ticker]
        matched = match_effective_date(as_of, eps_history.index, price_df.index)
        if matched is None:
            continue

        idx = eps_history.index.get_loc(matched)
        prior_idx = idx - QUARTERS_PER_YEAR
        if not isinstance(idx, int) or prior_idx < 0:
            continue  # not enough prior history yet for a YoY comparison

        current_eps = eps_history["reported_eps"].iloc[idx]
        prior_eps = eps_history["reported_eps"].iloc[prior_idx]
        if pd.isna(current_eps) or pd.isna(prior_eps) or prior_eps == 0:
            continue

        growth_pct = (current_eps - prior_eps) / abs(prior_eps) * 100
        if abs(growth_pct) < growth_threshold_pct:
            continue

        close = float(price_df.loc[as_of, "close"])
        rows.append(
            {
                "ticker": ticker,
                "date": as_of,
                "close": round(close, 2),
                "return_pct": 0.0,
                "return_zscore": round(growth_pct, 2),
                "volume_zscore": float("nan"),
                "direction": "up" if growth_pct > 0 else "dip",
            }
        )

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    result = pd.DataFrame(rows)
    return result.reindex(result["return_zscore"].abs().sort_values(ascending=False).index).reset_index(drop=True)
