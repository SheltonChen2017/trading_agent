"""
Analyst price-target consensus signal.

Genuinely different data category from signals/analyst.py's net-
upgrades/downgrades signal (rating DIRECTION, already tested and
REJECTED — see memory: project_signal_findings). This uses the actual
DOLLAR price targets analysts publish, aggregated into a point-in-time
trimmed consensus (see data/price_target_data.py), then flags a stock
when its current price diverges meaningfully from that consensus:

  - "dip": price trades notably BELOW the trimmed consensus target —
    analysts collectively think it's undervalued. The economically
    better-supported thesis: expect convergence upward toward the
    target (the "go long" hypothesis this project's whole backtest
    engine tests fits naturally here).
  - "up": price trades notably ABOVE the trimmed consensus target —
    analysts collectively think it's overvalued. Included for symmetry
    with every other signal in this project, NOT because there's a
    strong a priori reason to expect a "go long" bet on an overvalued
    stock to work — let the rigor toolkit decide, the same way
    momentum's academically-weaker "dip" leg was still tested.

`return_zscore` is repurposed to hold the actual gap %, same convention
as signals/fundamentals.py (a technical return z-score isn't the
relevant concept for an event/valuation-style signal); `volume_zscore`
is left NaN for the same reason. Same output contract as every other
signal in this project otherwise, so it plugs into the whole backtest/
rigor toolkit unchanged.

Usage (event-driven signals need a second bound argument — same pattern
as PEAD/fundamentals):

    from functools import partial
    from data.price_target_data import fetch_price_target_history
    from signals.analyst_target import scan_analyst_target_gap

    price_targets = fetch_price_target_history(list(data.keys()))
    run_backtest(data, scan_fn=partial(scan_analyst_target_gap, price_target_history=price_targets), scan_kwargs={})
"""
from __future__ import annotations

import pandas as pd

from config import ANALYST_TARGET_GAP_THRESHOLD_PCT
from data.price_target_data import compute_consensus_price_target

RESULT_COLUMNS = ["ticker", "date", "close", "return_pct", "return_zscore", "volume_zscore", "direction"]


def scan_analyst_target_gap(
    data: dict[str, pd.DataFrame],
    price_target_history: dict[str, pd.DataFrame],
    as_of: pd.Timestamp | None = None,
    gap_threshold_pct: float = ANALYST_TARGET_GAP_THRESHOLD_PCT,
) -> pd.DataFrame:
    """
    Flag a stock when the gap between its point-in-time trimmed
    consensus price target and its current close exceeds
    `gap_threshold_pct` in either direction. Requires
    `price_target_history` (from data.price_target_data.
    fetch_price_target_history()). Checked as-of any trading date (not
    tied to a specific disclosure event, unlike PEAD/fundamentals) —
    the analyst-consensus gap is a continuously-evolving state, not a
    one-time event.
    """
    if as_of is None:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    rows = []
    for ticker, price_df in data.items():
        if as_of not in price_df.index:
            continue
        history = price_target_history.get(ticker)
        if history is None or history.empty:
            continue

        consensus = compute_consensus_price_target(history, as_of)
        if consensus is None:
            continue

        close_price = float(price_df.loc[as_of, "close"])
        if close_price <= 0:
            continue
        gap_pct = (consensus - close_price) / close_price * 100

        if abs(gap_pct) < gap_threshold_pct:
            continue

        rows.append(
            {
                "ticker": ticker,
                "date": as_of,
                "close": round(close_price, 2),
                "return_pct": 0.0,
                "return_zscore": round(gap_pct, 2),
                "volume_zscore": float("nan"),
                "direction": "dip" if gap_pct > 0 else "up",
            }
        )

    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    result = pd.DataFrame(rows)
    return result.reindex(result["return_zscore"].abs().sort_values(ascending=False).index).reset_index(drop=True)
