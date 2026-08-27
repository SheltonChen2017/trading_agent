"""
Analyst price-target consensus signal.

This is a retained legacy/advisory surface, not Analyst Revisions V2 evidence.
V2 must not import or reinterpret this provider path.

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

import math
from numbers import Real

import pandas as pd

from config import ANALYST_TARGET_GAP_THRESHOLD_PCT
from data.price_target_data import (
    PriceTargetContractError,
    compute_consensus_price_target,
    validate_effective_session,
)

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
    as_of = validate_effective_session(as_of, "as_of")
    if (
        isinstance(gap_threshold_pct, bool)
        or not isinstance(gap_threshold_pct, Real)
        or not math.isfinite(float(gap_threshold_pct))
        or float(gap_threshold_pct) <= 0
    ):
        raise PriceTargetContractError(
            "gap_threshold_pct must be a finite positive number"
        )

    rows = []
    for ticker, price_df in data.items():
        if not isinstance(price_df, pd.DataFrame):
            raise PriceTargetContractError(f"{ticker}: price history must be a DataFrame")
        if not isinstance(price_df.index, pd.DatetimeIndex):
            raise PriceTargetContractError(f"{ticker}: price history needs a DatetimeIndex")
        if price_df.index.tz is not None:
            raise PriceTargetContractError(
                f"{ticker}: price history index must use timezone-free session labels"
            )
        if as_of not in price_df.index:
            continue
        if not price_df.index.is_unique:
            raise PriceTargetContractError(
                f"{ticker}: price history session labels must be unique"
            )
        if "close" not in price_df.columns:
            raise PriceTargetContractError(f"{ticker}: price history is missing close")
        history = price_target_history.get(ticker)
        if history is None:
            continue
        close_value = price_df.loc[as_of, "close"]
        if (
            isinstance(close_value, bool)
            or not isinstance(close_value, Real)
            or not math.isfinite(float(close_value))
            or float(close_value) <= 0
        ):
            raise PriceTargetContractError(
                f"{ticker}: close must be a finite positive number"
            )
        close_price = float(close_value)

        consensus = compute_consensus_price_target(history, as_of)
        if consensus is None:
            continue

        gap_pct = (consensus - close_price) / close_price * 100
        if not math.isfinite(gap_pct):
            raise PriceTargetContractError(f"{ticker}: computed target gap is non-finite")

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
