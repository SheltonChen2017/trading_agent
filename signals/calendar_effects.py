"""
Two market-wide calendar/session effects, sourced from a fresh literature
search on 2026-08-03: the overnight (close-to-open) drift, and the
turn-of-month effect. Both are UNCONDITIONAL -- every ticker, every day
either is or isn't "in the window" -- not a per-stock selection filter,
so neither fits the scan_fn(data, as_of) -> flagged-tickers contract every
other signal in signals/ follows. They instead produce one edge value per
(ticker, date) directly, meant to be fed straight into backtest/engine.py's
existing bootstrap_edge_significance_by_block() /
bootstrap_daily_edge_significance_by_block() -- the same block-bootstrap
primitives every other signal's significance test uses, just without the
scan_fn/entry_timing machinery those signals need to first pick WHICH
ticker-dates fire.

OVERNIGHT DRIFT (French & Roll 1986; recent survey evidence e.g. "Night
Moves", Elm Wealth 2022; Boyarchenko/Larsen/Whelan 2023 NY Fed). Claim:
almost all of a stock's long-run return accrues from close to next open,
essentially none from open to close. Robust and long-documented at the
INDEX level; per-stock evidence is thinner. IMPORTANT CAVEAT found during
the literature search (Liberty Street Economics, "The Disappearing
Overnight Drift", 2026): net of realistic trading/funding costs the
anomaly is not profitable, and the specific 2-3pm-window version of it has
been close to zero since 2021 -- i.e. there is live, recent evidence this
effect may already be decaying/gone. Treat a positive result here with
that in mind, not as confirmation of a stable tradeable edge.

  overnight_return_pct(ticker, t) = (open[t+1] - close[t]) / close[t] * 100

This project has no entry_timing mode that enters at a signal date's own
close and exits at the NEXT day's open (the three existing modes are
close-to-close, open-to-close same day, and next-open-to-later-open) --
building the actual close(t)->open(t+1) window here as a plain return
series, rather than adding a fourth mode to the shared run_backtest()
contract every existing finding depends on, is deliberate: this effect
needs its own bespoke harness regardless (see module docstring above),
so extending shared engine code would add risk to already-validated
signals for no reuse benefit.

TURN-OF-MONTH EFFECT (Ariel 1987; widely replicated, also widely noted as
weaker/less reliable post-publication like many seasonal anomalies).
Claim: stock returns are concentrated in a short window straddling the
calendar month boundary; other days average roughly zero.

  in_window(t)  = t is among the LAST `days_before` trading days of its
                  month, or the FIRST `days_after` trading days of the
                  following month
  edge(t)       = that day's own close-to-close return, for in-window
                  days only

FROZEN CONSTRUCTION (2026-08-03, before any result was observed):
  days_before = 1, days_after = 3  -- Ariel's original ~4-trading-day
                window (last day of month + first three of the next),
                the most commonly cited version of the effect

CAUGHT BY THE PROJECT'S OWN SYNTHETIC-DATA SANITY CHECK BEFORE ANY REAL
RUN: an earlier version of this test scored turn_of_month's raw window
return against a null of zero, exactly like overnight_drift. That is
wrong for THIS effect specifically. Ariel's hypothesis is COMPARATIVE --
turn-of-month days outperform other days -- not that turn-of-month days
have positive return in isolation. Under any general positive drift
(real bull markets included, and this project's synthetic generator has
one by construction), EVERY subset of days has a positive mean, so a
vs-zero test "confirmed" the effect on pure synthetic random-walk data,
which has no seasonal structure whatsoever -- a false positive caught
before it could contaminate a real-data conclusion. compute_turn_of_
month_returns() below still returns the RAW window return (useful as a
diagnostic and for other uses); the significance script subtracts each
ticker's own mean daily return over the SAME discovery/confirmation
period (matching backtest/engine.py's own_ticker_baseline_pct /
edge_vs_own_ticker_pct convention used by every scan_fn-based signal in
this project) before testing. overnight_drift does NOT need this
correction: its literature claim ("overnight returns are positive") is
itself an unconditional, vs-zero claim, and the same synthetic check
(module test below) found it near-zero exactly as expected on data with
no overnight-specific structure.
"""
from __future__ import annotations

import pandas as pd

TURN_OF_MONTH_DAYS_BEFORE = 1
TURN_OF_MONTH_DAYS_AFTER = 3


def compute_daily_returns(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    One row per (ticker, date) with that day's own close-to-close return,
    for EVERY trading day (not just turn-of-month days) -- the baseline
    population compute_turn_of_month_returns()'s window return must be
    compared against; see the "CAUGHT BY..." note in the module
    docstring for why. Columns: ticker, date, return_pct.
    """
    rows = []
    for ticker, df in data.items():
        if len(df) < 2:
            continue
        returns = df["close"].pct_change() * 100
        for date, value in returns.items():
            if pd.notna(value):
                rows.append({"ticker": ticker, "date": date, "return_pct": float(value)})

    return pd.DataFrame(rows, columns=["ticker", "date", "return_pct"])


def compute_overnight_returns(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    One row per (ticker, date) with the close(t) -> open(t+1) return, for
    every date that has a following trading day in that ticker's own
    history. Columns: ticker, date, edge_pct.
    """
    rows = []
    for ticker, df in data.items():
        if len(df) < 2:
            continue
        close = df["close"]
        next_open = df["open"].shift(-1)
        edge = (next_open - close) / close * 100
        edge = edge.iloc[:-1]  # last row has no next_open
        for date, value in edge.items():
            if pd.notna(value):
                rows.append({"ticker": ticker, "date": date, "edge_pct": float(value)})

    return pd.DataFrame(rows, columns=["ticker", "date", "edge_pct"])


def compute_turn_of_month_returns(
    data: dict[str, pd.DataFrame],
    days_before: int = TURN_OF_MONTH_DAYS_BEFORE,
    days_after: int = TURN_OF_MONTH_DAYS_AFTER,
) -> pd.DataFrame:
    """
    One row per (ticker, date) with that day's own close-to-close return,
    restricted to dates in the turn-of-month window: the last
    `days_before` trading days of a month, or the first `days_after`
    trading days of the following month. Columns: ticker, date, edge_pct.

    "Trading day of the month" is derived per-ticker from that ticker's
    own trading calendar (its index), not a generic business-day
    calendar, so a market holiday never miscounts which session is
    actually the Nth-from-the-end/start.
    """
    if days_before < 1:
        raise ValueError(f"days_before must be at least 1, got {days_before!r}.")
    if days_after < 1:
        raise ValueError(f"days_after must be at least 1, got {days_after!r}.")

    rows = []
    for ticker, df in data.items():
        if len(df) < 2:
            continue
        returns = df["close"].pct_change() * 100
        month_period = df.index.to_series().dt.to_period("M")

        # Rank each trading day within its own month, from both ends,
        # using ONLY that ticker's own actual trading dates.
        day_rank_from_start = month_period.groupby(month_period).cumcount()
        day_rank_from_end = month_period.groupby(month_period).cumcount(ascending=False)

        is_window_end = day_rank_from_end < days_before
        # "First days_after days of the FOLLOWING month" == every date
        # whose rank-from-start is within days_after of the PREVIOUS
        # calendar month's boundary; simplest correct expression: shift
        # the "near month start" mask back onto the month that precedes
        # it isn't needed -- a date is in this leg directly if its own
        # rank_from_start < days_after AND it isn't the very first month
        # in the ticker's history (no defined "previous month" boundary
        # to straddle).
        is_window_start = day_rank_from_start < days_after
        first_month = month_period.iloc[0] if len(month_period) else None
        is_window_start &= month_period != first_month

        in_window = is_window_end | is_window_start

        for date, ret, flag in zip(df.index, returns, in_window):
            if flag and pd.notna(ret):
                rows.append({"ticker": ticker, "date": date, "edge_pct": float(ret)})

    return pd.DataFrame(rows, columns=["ticker", "date", "edge_pct"])
